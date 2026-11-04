"""Per-section flashcard generation."""
import logging
import random
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from ..llm import generate_json
from .chunking import Section
from .textclean import strip_passage_references

log = logging.getLogger("studysnap.flashcards")

CardType = Literal[
    "definition", "concept", "formula", "process", "comparison", "cause_effect", "example", "fact"
]
MAX_CARDS_PER_SECTION = 12
MIN_CARDS_PER_SECTION = 2


CardFormat = Literal["qa", "cloze", "true_false", "mcq"]
BLANK = "_____"

# A "qa" front must be a real question or an instruction, never a bare topic like "Definition of an Algorithm".
_QUESTION_STARTS = (
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how", "is", "are", "does", "do", "did",
    "can", "could", "should", "will", "would", "define", "explain", "state", "list", "describe", "name", "give",
    "compare", "contrast", "differentiate", "distinguish", "write", "identify", "outline", "summarize",
    "calculate", "derive", "prove", "show", "complete", "trace", "convert", "determine", "find",
)
_NONE_OF_ABOVE = ("all of the above", "none of the above", "both a and b")


class _CardOut(BaseModel):
    front: str
    back: str
    type: CardType
    format: CardFormat
    options: list[str] = []
    importance: int


class _CardBatch(BaseModel):
    cards: list[_CardOut]


@dataclass
class RawCard:
    chapter_idx: int
    front: str
    back: str
    card_type: str
    importance: int
    page: int
    fmt: str = "qa"
    options: list[str] | None = None


MODE_HINT = {
    "exam": (
        "Prefer what an exam would test: definitions, formulas, key facts, step-by-step processes, "
        "comparisons, and cause-and-effect relationships."
    ),
    "overview": "Prefer the main ideas, themes, and how the concepts relate to each other.",
}

SYSTEM = """You are an expert teacher who writes study flashcards from a textbook passage.

Rules:
- Use ONLY information stated in the passage. Never add outside facts.
- Each card tests exactly one idea and must make sense on its own (no "in the passage", "the author", "this chapter").
- The "front" must be SPECIFIC and answerable: a direct question or an instruction. Never a bare topic or title.
  Bad: "Definition of an Algorithm", "Input and Output in Algorithms", "Halting".
  Good: "Define an algorithm.", "What do the input and output of an algorithm represent?", "What does it mean for an algorithm to halt?"
- "format" decides the shape of the card. Use a mix, roughly 45% qa, 20% cloze, 20% mcq, 15% true_false:
  * qa: "front" is a specific question or an instruction ("Define ...", "Explain why ...", "List the steps of ..."). "back" is a concise answer of 1-3 sentences. "options" is [].
  * cloze: "front" is ONE sentence from the passage with the key term replaced by _____ (exactly one blank). "back" is just the missing word or phrase. "options" is [].
  * true_false: "front" is a single statement, either true or false according to the passage (make about half of them false by changing one key fact). "back" starts with "True." or "False." followed by a one-sentence reason. "options" is [].
  * mcq: "front" is a specific question. "options" has exactly 4 short, plausible, distinct choices with the CORRECT one FIRST (it is shuffled later); never "all/none of the above". "back" is a one-sentence explanation of why the correct choice is right.
- "type" is one of: definition, concept, formula, process, comparison, cause_effect, example, fact.
- "importance" is an integer 1-5: 5 = core idea every student must know, 3 = useful supporting point, 1 = minor detail.
- Skip trivia, anecdotes, page references and anything the passage only mentions in passing.
- {mode_hint}
- Write exactly {count} cards. Write fewer only if the passage does not contain enough substance."""


def cards_for_section_count(pool_total: int, section_words: int, total_words: int) -> int:
    raw = round(pool_total * section_words / max(total_words, 1))
    return max(MIN_CARDS_PER_SECTION, min(MAX_CARDS_PER_SECTION, raw))


def _valid(card: _CardOut) -> bool:
    front, back = card.front.strip(), card.back.strip()
    if not (5 <= len(front) <= 300 and 1 <= len(back) <= 700 and front.lower() != back.lower()):
        return False
    if card.format == "cloze":
        return front.count(BLANK) == 1 and len(back) <= 80
    if card.format == "true_false":
        return back.lower().startswith(("true", "false"))
    if card.format == "mcq":
        opts = [o.strip() for o in card.options]
        return (
            len(opts) == 4
            and all(opts)
            and len({o.lower() for o in opts}) == 4
            and not any(o.lower().rstrip(".") in _NONE_OF_ABOVE for o in opts)
            and front.endswith("?")
        )
    return front.endswith("?") or front.lower().startswith(_QUESTION_STARTS)


def _finish(card: _CardOut, rng: random.Random) -> tuple[str, str, list[str] | None]:
    """Clean the text and, for mcq, shuffle the choices and name the right one in the back."""
    front = strip_passage_references(card.front.strip())
    back = strip_passage_references(card.back.strip())
    if card.format == "true_false":
        front = re.sub(r"^\s*(true\s*(or|/)\s*false\s*[:?.\-–—]*\s*)+", "", front, flags=re.IGNORECASE)
        return f"True or false: {front}", back, None
    if card.format == "mcq":
        opts = [o.strip() for o in card.options]
        correct = opts[0]
        rng.shuffle(opts)
        letter = "ABCD"[opts.index(correct)]
        return front, f"{letter}. {correct}\n{back}", opts
    return front, back, None


def generate_for_section(section: Section, chapter_title: str, count: int, mode: str) -> list[RawCard]:
    system = SYSTEM.format(mode_hint=MODE_HINT.get(mode, MODE_HINT["exam"]), count=count)
    user = f"Chapter: {chapter_title}\n\nPassage:\n{section.text}"
    batch = generate_json(system, user, _CardBatch)
    if batch is None:
        log.warning("No valid cards for chapter %s section %s", section.chapter_idx, section.idx)
        return []
    out: list[RawCard] = []
    seen: set[str] = set()
    rng = random.Random(f"{section.chapter_idx}-{section.idx}")
    for c in batch.cards:
        if not _valid(c):
            continue
        key = c.front.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        front, back, options = _finish(c, rng)
        out.append(
            RawCard(
                chapter_idx=section.chapter_idx,
                front=front,
                back=back,
                card_type=c.type,
                importance=min(5, max(1, int(c.importance))),
                page=section.page_start,
                fmt=c.format,
                options=options,
            )
        )
    return out
