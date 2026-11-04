"""Split chapters into model-sized sections on paragraph/sentence boundaries."""
import re
from dataclasses import dataclass

from .extract import Chapter

MAX_SECTION_WORDS = 1800
MIN_SECTION_WORDS = 250

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


@dataclass
class Section:
    chapter_idx: int
    idx: int  # position within the chapter
    text: str
    page_start: int
    page_end: int

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def _units(text: str, max_words: int) -> list[str]:
    """Paragraphs; paragraphs longer than max_words are split into sentence groups."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        if not para:
            continue
        if len(para.split()) <= max_words:
            out.append(para)
            continue
        current: list[str] = []
        count = 0
        for sentence in _SENTENCE_RE.split(para):
            w = len(sentence.split())
            if current and count + w > max_words:
                out.append(" ".join(current))
                current, count = [], 0
            current.append(sentence)
            count += w
        if current:
            out.append(" ".join(current))
    return out


def split_chapter(chapter: Chapter, max_words: int = MAX_SECTION_WORDS) -> list[Section]:
    sections: list[Section] = []
    buf: list[str] = []
    buf_words = 0
    first_page = last_page = chapter.page_start

    def flush() -> None:
        nonlocal buf, buf_words, first_page
        if buf:
            sections.append(
                Section(chapter.idx, len(sections), "\n\n".join(buf), first_page, last_page)
            )
        buf, buf_words = [], 0

    for page_no, text in chapter.pages:
        for unit in _units(text, max_words):
            w = len(unit.split())
            if buf and buf_words + w > max_words:
                flush()
            if not buf:
                first_page = page_no
            buf.append(unit)
            buf_words += w
            last_page = page_no
    flush()

    # fold a short trailing section into the previous one
    if len(sections) > 1 and sections[-1].word_count < MIN_SECTION_WORDS:
        tail = sections.pop()
        prev = sections[-1]
        prev.text += "\n\n" + tail.text
        prev.page_end = tail.page_end
    for i, s in enumerate(sections):
        s.idx = i
    return sections


def split_book(chapters: list[Chapter]) -> list[Section]:
    out: list[Section] = []
    for ch in chapters:
        out.extend(split_chapter(ch))
    return out
