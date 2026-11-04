"""Runs one job end to end: download -> extract -> generate -> store."""
import logging
import math
import random
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from ..db import admin
from .. import llm
from . import explainer, flashcards, quiz
from .chunking import Section, split_book
from .extract import ExtractedBook, ExtractionError, extract_book, looks_like_pdf
from .ranking import Card, dedupe_by_embedding, normalize, score_cards, select_top_n

log = logging.getLogger("studysnap.runner")

POOL_FACTOR = 2.5  # generate this many times the requested cards, then keep the best N
INSERT_BATCH = 100


class JobFailed(RuntimeError):
    """A failure whose message is safe to show to the user."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Progress:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    def set(self, status: str, progress: int, message: str | None = None) -> None:
        admin().table("jobs").update(
            {"status": status, "progress": max(0, min(100, int(progress))), "message": message}
        ).eq("id", self.job_id).execute()


def _batched(rows: list[dict[str, Any]], size: int = INSERT_BATCH):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _load_book(job: dict[str, Any]) -> dict[str, Any]:
    res = admin().table("books").select("*").eq("id", job["book_id"]).eq("user_id", job["user_id"]).limit(1).execute()
    if not res.data:
        raise JobFailed("The book no longer exists.")
    return res.data[0]


def _download_and_extract(book: dict[str, Any]) -> ExtractedBook:
    try:
        data = admin().storage.from_(settings.books_bucket).download(book["storage_path"])
    except Exception as exc:
        raise JobFailed("Could not download the uploaded file.") from exc
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise JobFailed(f"The file is larger than {settings.max_upload_mb} MB.")
    if not looks_like_pdf(data):
        raise JobFailed("The uploaded file is not a PDF.")
    try:
        return extract_book(data)
    except ExtractionError as exc:
        raise JobFailed(str(exc)) from exc


def _sync_chapters(book: dict[str, Any], extracted: ExtractedBook) -> dict[int, str]:
    """Upsert chapter rows (stable by index) and return idx -> chapter id."""
    rows = [
        {
            "book_id": book["id"],
            "user_id": book["user_id"],
            "idx": c.idx,
            "title": c.title[:300],
            "page_start": c.page_start,
            "page_end": c.page_end,
            "word_count": c.word_count,
        }
        for c in extracted.chapters
    ]
    res = admin().table("chapters").upsert(rows, on_conflict="book_id,idx").execute()
    admin().table("chapters").delete().eq("book_id", book["id"]).gte("idx", len(rows)).execute()
    admin().table("books").update({"page_count": extracted.page_count}).eq("id", book["id"]).execute()
    return {r["idx"]: r["id"] for r in res.data}


def _check_ollama() -> None:
    status = llm.health()
    if not status["reachable"]:
        raise JobFailed("The AI service (Ollama) is not reachable. Start it with `ollama serve`.")
    if status["missing_models"]:
        pulls = ", ".join(f"`ollama pull {m}`" for m in status["missing_models"])
        raise JobFailed(f"Required AI models are missing. Run: {pulls}")


def _run_study(job: dict[str, Any], book: dict[str, Any], extracted: ExtractedBook,
               chapter_ids: dict[int, str], progress: Progress) -> None:
    opts = job["options"]
    n_cards = int(opts.get("n_cards", 100))
    mode = opts.get("mode", "exam")
    include_quiz = bool(opts.get("include_quiz", True))
    quiz_total = int(opts.get("quiz_questions", 30))

    chapter_title = {c.idx: c.title for c in extracted.chapters}
    chapter_words = {c.idx: c.word_count for c in extracted.chapters}
    chapter_text = {c.idx: " ".join(t for _, t in c.pages) for c in extracted.chapters}
    sections = split_book(extracted.chapters)
    total_words = sum(s.word_count for s in sections) or 1
    pool_total = math.ceil(n_cards * POOL_FACTOR)

    # ---- flashcards: generate a pool per section
    raw: list[flashcards.RawCard] = []
    for i, s in enumerate(sections):
        progress.set("generating", 8 + 52 * i / len(sections),
                     f"Flashcards: section {i + 1} of {len(sections)}")
        count = flashcards.cards_for_section_count(pool_total, s.word_count, total_words)
        raw.extend(flashcards.generate_for_section(s, chapter_title[s.chapter_idx], count, mode))
    if not raw:
        raise JobFailed("The AI model did not return any usable flashcards. Try again, or try a different model.")

    # ---- rank the whole pool and keep the top N
    progress.set("ranking", 62, "Ranking flashcards by importance")
    vectors = normalize(llm.embed([f"{c.front}\n{c.back}" for c in raw]))
    cards = [
        Card(r.chapter_idx, r.front, r.back, r.card_type, r.importance, r.page, r.fmt, r.options, embedding=v)
        for r, v in zip(raw, vectors)
    ]
    score_cards(cards, chapter_text, chapter_title, mode)
    select_top_n(cards, chapter_words, n_cards)

    admin().table("flashcards").delete().eq("book_id", book["id"]).execute()
    rows = [
        {
            "book_id": book["id"],
            "user_id": book["user_id"],
            "chapter_id": chapter_ids.get(c.chapter_idx),
            "front": c.front,
            "back": c.back,
            "card_type": c.card_type,
            "format": c.fmt,
            "options": c.options,
            "importance": c.importance,
            "score": round(c.score, 4),
            "rank": c.rank,
            "selected": c.selected,
            "source_page": c.page,
        }
        for c in sorted(cards, key=lambda c: c.rank)
    ]
    for batch in _batched(rows):
        admin().table("flashcards").insert(batch).execute()

    # ---- quiz
    if include_quiz:
        _run_quiz(book, sections, chapter_title, chapter_ids, quiz_total, progress)

    progress.set("completed", 100, f"{sum(c.selected for c in cards)} flashcards ready")


def _run_quiz(book: dict[str, Any], sections: list[Section], chapter_title: dict[int, str],
              chapter_ids: dict[int, str], quiz_total: int, progress: Progress) -> None:
    rng = random.Random(book["id"])
    counts = quiz.question_counts(math.ceil(quiz_total * 1.3), [float(s.word_count) for s in sections])
    work = [(s, c) for s, c in zip(sections, counts) if c > 0]

    questions: list[quiz.RawQuestion] = []
    shortfalls: list[tuple[Section, int]] = []
    for i, (s, c) in enumerate(work):
        progress.set("quiz", 65 + 30 * i / max(1, len(work)), f"Quiz: section {i + 1} of {len(work)}")
        got = quiz.generate_for_section(s, chapter_title[s.chapter_idx], c, rng)
        questions.extend(got)
        if len(got) < c:
            shortfalls.append((s, c - len(got)))

    # The model sometimes returns fewer questions than asked: top up once from those sections.
    if len(questions) < quiz_total and shortfalls:
        for s, missing in shortfalls:
            progress.set("quiz", 94, "Quiz: filling gaps")
            questions.extend(quiz.generate_for_section(s, chapter_title[s.chapter_idx], missing, rng))

    generated = len(questions)
    if questions:
        vectors = normalize(llm.embed([q.question for q in questions]))
        questions = [questions[i] for i in dedupe_by_embedding(vectors)]
    log.info("Quiz: asked for %d, valid %d, after dedupe %d, keeping up to %d",
             sum(c for _, c in work), generated, len(questions), quiz_total)
    if len(questions) > quiz_total:
        keep = sorted(rng.sample(range(len(questions)), quiz_total))
        questions = [questions[i] for i in keep]

    admin().table("quiz_questions").delete().eq("book_id", book["id"]).execute()
    rows = [
        {
            "book_id": book["id"],
            "user_id": book["user_id"],
            "chapter_id": chapter_ids.get(q.chapter_idx),
            "question": q.question,
            "options": q.options,
            "correct_index": q.correct_index,
            "explanation": q.explanation,
            "source_page": q.page,
        }
        for q in questions
    ]
    for batch in _batched(rows):
        admin().table("quiz_questions").insert(batch).execute()


def _run_explainer(job: dict[str, Any], book: dict[str, Any], extracted: ExtractedBook,
                   chapter_ids: dict[int, str], progress: Progress) -> None:
    level = job["options"].get("level", "student")
    all_sections = split_book(extracted.chapters)
    by_chapter: dict[int, list[Section]] = {}
    for s in all_sections:
        by_chapter.setdefault(s.chapter_idx, []).append(s)

    done = 0
    results: list[explainer.ChapterResult] = []
    chapter_rows: list[dict[str, Any]] = []
    for ch in extracted.chapters:
        section_results: list[explainer.SectionResult] = []
        for s in by_chapter.get(ch.idx, []):
            progress.set("explaining", 5 + 85 * done / max(1, len(all_sections)),
                         f"Explaining chapter {ch.idx + 1} of {len(extracted.chapters)}")
            res = explainer.explain_section(s, ch.title, level)
            if res is not None:
                section_results.append(res)
            done += 1
        if not section_results:
            continue
        chapter_result = explainer.explain_chapter(ch.title, section_results, level)
        results.append(chapter_result)
        chapter_rows.append({
            "book_id": book["id"],
            "user_id": book["user_id"],
            "chapter_id": chapter_ids.get(ch.idx),
            "level": level,
            "title": ch.title[:300],
            "content_md": chapter_result.markdown,
            "key_terms": chapter_result.terms,
        })
    if not results:
        raise JobFailed("The AI model did not return any usable explanations. Try again, or try a different model.")

    progress.set("explaining", 92, "Writing the book overview")
    book_md, glossary = explainer.explain_book(book["title"], results, level)

    admin().table("explanations").delete().eq("book_id", book["id"]).eq("level", level).execute()
    book_row = {
        "book_id": book["id"], "user_id": book["user_id"], "chapter_id": None, "level": level,
        "title": book["title"][:300], "content_md": book_md, "key_terms": glossary,
    }
    for batch in _batched([book_row] + chapter_rows):
        admin().table("explanations").insert(batch).execute()
    progress.set("completed", 100, "Explainer ready")


def run_job(job: dict[str, Any]) -> None:
    progress = Progress(job["id"])
    admin().table("jobs").update({"started_at": _now(), "status": "extracting", "progress": 1,
                                  "message": "Reading the book"}).eq("id", job["id"]).execute()
    book = _load_book(job)
    admin().table("books").update({"status": "processing"}).eq("id", book["id"]).execute()

    _check_ollama()
    extracted = _download_and_extract(book)
    progress.set("extracting", 6, f"Found {len(extracted.chapters)} chapters")
    chapter_ids = _sync_chapters(book, extracted)

    if job["kind"] == "study":
        _run_study(job, book, extracted, chapter_ids, progress)
    else:
        _run_explainer(job, book, extracted, chapter_ids, progress)


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, JobFailed):
        return str(exc)
    if isinstance(exc, llm.LLMError):
        return "The AI model stopped responding. Make sure `ollama serve` is running, then retry."
    return "Something went wrong while processing this book. Check the backend logs."
