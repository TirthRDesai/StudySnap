"""PDF text extraction and chapter detection."""
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are noisy and harmless

MIN_BOOK_WORDS = 300
MIN_CHAPTER_WORDS = 150
FALLBACK_PAGES_PER_PART = 15

_CHAPTER_RE = re.compile(
    r"^\s*(chapter|unit|part|lesson|module)\s+([0-9]+|[ivxlc]+|one|two|three|four|five|six|seven|eight|nine|ten)\b[\s:.\-–—]*(.*)$",
    re.IGNORECASE,
)


class ExtractionError(ValueError):
    """The PDF can't be turned into usable text (encrypted, scanned, empty...)."""


@dataclass
class Chapter:
    idx: int
    title: str
    page_start: int  # 1-based, inclusive
    page_end: int
    pages: list[tuple[int, str]] = field(default_factory=list)  # (page number, cleaned text)

    @property
    def word_count(self) -> int:
        return sum(len(t.split()) for _, t in self.pages)


@dataclass
class ExtractedBook:
    page_count: int
    chapters: list[Chapter]

    @property
    def word_count(self) -> int:
        return sum(c.word_count for c in self.chapters)


def looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def _clean_pages(raw_pages: list[str]) -> list[str]:
    """Drop repeated headers/footers and bare page numbers, and re-join hyphenated words."""
    n = len(raw_pages)
    line_counts: Counter[str] = Counter()
    for text in raw_pages:
        for line in {ln.strip() for ln in text.splitlines() if ln.strip()}:
            line_counts[re.sub(r"\d+", "#", line)] += 1

    threshold = max(4, int(n * 0.4))
    cleaned: list[str] = []
    for text in raw_pages:
        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                kept.append("")
                continue
            if re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", stripped):
                continue  # page number
            if n >= 8 and line_counts[re.sub(r"\d+", "#", stripped)] >= threshold and len(stripped) < 100:
                continue  # running header/footer
            kept.append(stripped)
        joined = "\n".join(kept)
        joined = re.sub(r"(\w)-\n(\w)", r"\1\2", joined)  # de-hyphenate
        joined = re.sub(r"[ \t]+", " ", joined)
        cleaned.append(joined.strip())
    return cleaned


def _outline_chapters(reader: PdfReader, page_count: int) -> list[tuple[str, int]]:
    """Top-level bookmarks as (title, 0-based page index)."""
    try:
        outline = reader.outline
    except Exception:
        return []
    found: list[tuple[str, int]] = []
    for item in outline:
        if isinstance(item, list):
            continue  # nested children: only keep top level
        try:
            title = str(item.title).strip()
            page = reader.get_destination_page_number(item)
        except Exception:
            continue
        if title and 0 <= page < page_count:
            found.append((title, page))
    # keep first bookmark per page, in page order
    seen: set[int] = set()
    result: list[tuple[str, int]] = []
    for title, page in sorted(found, key=lambda t: t[1]):
        if page not in seen:
            seen.add(page)
            result.append((title, page))
    return result


def _heading_chapters(pages: list[str]) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for i, text in enumerate(pages):
        for line in [ln.strip() for ln in text.splitlines() if ln.strip()][:4]:
            m = _CHAPTER_RE.match(line)
            if m and len(line) < 120:
                found.append((line, i))
                break
    return found


def _build_chapters(starts: list[tuple[str, int]], pages: list[str]) -> list[Chapter]:
    chapters: list[Chapter] = []
    if starts and starts[0][1] > 0:
        starts = [("Introduction", 0)] + starts
    for i, (title, start) in enumerate(starts):
        end = starts[i + 1][1] - 1 if i + 1 < len(starts) else len(pages) - 1
        chapters.append(
            Chapter(
                idx=i,
                title=title,
                page_start=start + 1,
                page_end=end + 1,
                pages=[(p + 1, pages[p]) for p in range(start, end + 1) if pages[p].strip()],
            )
        )
    return chapters


def _merge_small(chapters: list[Chapter]) -> list[Chapter]:
    """Fold tiny chapters (front matter, divider pages) into the previous chapter."""
    merged: list[Chapter] = []
    for ch in chapters:
        if merged and ch.word_count < MIN_CHAPTER_WORDS:
            prev = merged[-1]
            prev.pages.extend(ch.pages)
            prev.page_end = ch.page_end
        else:
            merged.append(ch)
    if len(merged) > 1 and merged[0].word_count < MIN_CHAPTER_WORDS:
        first = merged.pop(0)
        merged[0].pages = first.pages + merged[0].pages
        merged[0].page_start = first.page_start
    for i, ch in enumerate(merged):
        ch.idx = i
    return merged


_REFERENCES_RE = re.compile(r"^\s*(?:[0-9ivxl]+[.)]?\s+)?(references|bibliography|works cited)\s*:?\s*$", re.IGNORECASE)


def _drop_references(chapters: list[Chapter]) -> list[Chapter]:
    """Cut each chapter at its References/Bibliography heading: citation lists make junk flashcards."""
    kept: list[Chapter] = []
    for ch in chapters:
        pages: list[tuple[int, str]] = []
        cut = False
        for page_no, text in ch.pages:
            lines = text.split("\n")
            hit = next((i for i, ln in enumerate(lines) if _REFERENCES_RE.match(ln)), None)
            if hit is not None:
                before = "\n".join(lines[:hit]).strip()
                if before:
                    pages.append((page_no, before))
                cut = True
                break
            pages.append((page_no, text))
        if cut:
            ch.pages = pages
            if pages:
                ch.page_end = pages[-1][0]
        if ch.pages:
            kept.append(ch)
    for i, ch in enumerate(kept):
        ch.idx = i
    return kept


def extract_book(data: bytes) -> ExtractedBook:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise ExtractionError("This file could not be read as a PDF.") from exc
    if reader.is_encrypted:
        raise ExtractionError("Password-protected PDFs are not supported.")

    page_count = len(reader.pages)
    raw: list[str] = []
    for page in reader.pages:
        try:
            raw.append(page.extract_text() or "")
        except Exception:
            raw.append("")
    pages = _clean_pages(raw)

    if sum(len(t.split()) for t in pages) < MIN_BOOK_WORDS:
        raise ExtractionError(
            "Not enough text found. Scanned or image-only PDFs are not supported yet."
        )

    starts = _outline_chapters(reader, page_count)
    if len(starts) < 2:
        starts = _heading_chapters(pages)
    if len(starts) < 2:
        starts = [(f"Part {i // FALLBACK_PAGES_PER_PART + 1}", i) for i in range(0, page_count, FALLBACK_PAGES_PER_PART)]

    chapters = _drop_references(_merge_small(_build_chapters(starts, pages)))
    if not chapters or sum(c.word_count for c in chapters) < MIN_BOOK_WORDS:
        raise ExtractionError("Could not find any readable content.")
    return ExtractedBook(page_count=page_count, chapters=chapters)
