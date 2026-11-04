"""Hierarchical plain-language explainer: sections -> chapter -> book."""
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel

from ..llm import generate_json
from .chunking import Section

log = logging.getLogger("studysnap.explainer")

LEVEL_STYLE = {
    "eli5": (
        "Explain it to a curious 12-year-old: simple everyday words, short sentences, and a friendly "
        "analogy. Avoid jargon; when a technical word is unavoidable, explain it right away."
    ),
    "student": (
        "Explain it to a first-year university student: clear language, define technical terms when "
        "they first appear, and add a short example where it helps."
    ),
    "detailed": (
        "Explain it in depth for a motivated learner: keep the technical accuracy, spell out the "
        "reasoning and the nuances, and define every technical term."
    ),
}

MAX_CHAPTER_INPUT_WORDS = 4500
MAX_GLOSSARY_TERMS = 60


class _Term(BaseModel):
    term: str
    meaning: str


class _SectionExplanation(BaseModel):
    heading: str
    explanation: str
    key_terms: list[_Term]
    why_it_matters: str


class _ChapterOverview(BaseModel):
    main_idea: str
    how_it_connects: str
    remember_this: list[str]


class _BookOverview(BaseModel):
    summary: str
    big_ideas: list[str]


@dataclass
class SectionResult:
    heading: str
    markdown: str
    terms: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ChapterResult:
    title: str
    markdown: str
    main_idea: str
    terms: list[dict[str, str]]


SECTION_SYSTEM = """You turn a textbook passage into a clear explanation for a learner.

{style}

Rules:
- Base the explanation ONLY on the passage. If something is not covered, do not make it up.
- "heading" is a short descriptive title (max 8 words).
- "explanation" is 2-4 short paragraphs of Markdown. You may use **bold** for key terms and bullet lists when they help.
- "key_terms" lists up to 5 important terms from the passage with a one-sentence plain meaning each.
- "why_it_matters" is one sentence on why this idea is important."""

CHAPTER_SYSTEM = """You write the overview of one textbook chapter from explanations of its sections.

{style}

Rules:
- Use only the material given.
- "main_idea" is 2-3 sentences: what this chapter is about.
- "how_it_connects" is 2-3 sentences on how its sections build on each other.
- "remember_this" is 3 short takeaways."""

BOOK_SYSTEM = """You write the overview of a whole book from short summaries of its chapters.

{style}

Rules:
- Use only the material given.
- "summary" is 1-2 short paragraphs on what the book covers and how it is organised.
- "big_ideas" is 4-7 of the most important ideas across the book, one sentence each."""


def explain_section(section: Section, chapter_title: str, level: str) -> SectionResult | None:
    system = SECTION_SYSTEM.format(style=LEVEL_STYLE[level])
    user = f"Chapter: {chapter_title}\n\nPassage:\n{section.text}"
    out = generate_json(system, user, _SectionExplanation)
    if out is None or not out.explanation.strip():
        log.warning("No explanation for chapter %s section %s", section.chapter_idx, section.idx)
        return None
    heading = out.heading.strip() or f"Section {section.idx + 1}"
    parts = [f"### {heading}", "", out.explanation.strip()]
    if out.why_it_matters.strip():
        parts += ["", f"**Why it matters:** {out.why_it_matters.strip()}"]
    terms = [
        {"term": t.term.strip(), "meaning": t.meaning.strip()}
        for t in out.key_terms
        if t.term.strip() and t.meaning.strip()
    ]
    return SectionResult(heading=heading, markdown="\n".join(parts), terms=terms)


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    return text if len(words) <= limit else " ".join(words[:limit])


def explain_chapter(title: str, sections: list[SectionResult], level: str) -> ChapterResult:
    """Combine section explanations and add a chapter-level overview built from them."""
    body = "\n\n".join(s.markdown for s in sections)
    terms = [t for s in sections for t in s.terms]
    overview = None
    if sections:
        system = CHAPTER_SYSTEM.format(style=LEVEL_STYLE[level])
        user = f"Chapter: {title}\n\nSection explanations:\n{_truncate_words(body, MAX_CHAPTER_INPUT_WORDS)}"
        overview = generate_json(system, user, _ChapterOverview)

    head: list[str] = []
    main_idea = ""
    if overview is not None:
        main_idea = overview.main_idea.strip()
        head = [f"> {main_idea}", "", overview.how_it_connects.strip()]
    tail: list[str] = []
    if overview is not None and overview.remember_this:
        tail = ["", "### If you remember one thing", ""] + [f"- {x.strip()}" for x in overview.remember_this if x.strip()]
    markdown = "\n".join(head + ["", body] + tail).strip()
    return ChapterResult(title=title, markdown=markdown, main_idea=main_idea, terms=terms)


def explain_book(book_title: str, chapters: list[ChapterResult], level: str) -> tuple[str, list[dict[str, str]]]:
    """Return (markdown, glossary terms) for the whole-book overview."""
    lines = [f"{i + 1}. {c.title}: {c.main_idea or 'n/a'}" for i, c in enumerate(chapters[:80])]
    overview = generate_json(
        BOOK_SYSTEM.format(style=LEVEL_STYLE[level]),
        f"Book: {book_title}\n\nChapters:\n" + "\n".join(lines),
        _BookOverview,
    )

    seen: set[str] = set()
    glossary: list[dict[str, str]] = []
    for c in chapters:
        for t in c.terms:
            key = t["term"].lower()
            if key not in seen and len(glossary) < MAX_GLOSSARY_TERMS:
                seen.add(key)
                glossary.append(t)
    glossary.sort(key=lambda t: t["term"].lower())

    parts: list[str] = []
    if overview is not None:
        parts += [overview.summary.strip(), "", "### Big ideas", ""]
        parts += [f"- {x.strip()}" for x in overview.big_ideas if x.strip()]
    parts += ["", "### Chapters", ""]
    parts += [f"{i + 1}. **{c.title}**" + (f" — {c.main_idea}" if c.main_idea else "") for i, c in enumerate(chapters)]
    return "\n".join(parts).strip(), glossary
