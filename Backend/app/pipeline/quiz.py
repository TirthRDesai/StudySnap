"""Multiple-choice quiz generation, per section."""
import logging
import random
from dataclasses import dataclass

from pydantic import BaseModel

from ..llm import generate_json
from .chunking import Section
from .textclean import strip_passage_references

log = logging.getLogger("studysnap.quiz")

MAX_QUESTIONS_PER_SECTION = 6


class _QuestionOut(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class _QuizBatch(BaseModel):
    questions: list[_QuestionOut]


@dataclass
class RawQuestion:
    chapter_idx: int
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    page: int


SYSTEM = """You are an expert teacher who writes multiple-choice exam questions from a textbook passage.

Rules:
- Use ONLY information stated in the passage. Never add outside facts.
- Write exactly {count} questions (fewer only if the passage lacks substance). Each tests a different idea.
- Each question must make sense on its own (no "according to the passage", "the author", "this chapter").
- Exactly 4 options. Exactly one is correct; "correct_index" is its position (0-3).
- Wrong options must be plausible but clearly wrong according to the passage. Never use "all of the above" or "none of the above".
- Keep options short and similar in length and style.
- "explanation" is one sentence saying why the correct option is right."""


def question_counts(target_total: int, weights: list[float]) -> list[int]:
    from .ranking import allocate

    return [min(MAX_QUESTIONS_PER_SECTION, c) for c in allocate(target_total, weights, 0)]


def validate(q: _QuestionOut) -> bool:
    opts = [o.strip() for o in q.options]
    if len(opts) != 4 or any(not o for o in opts):
        return False
    if len({o.lower() for o in opts}) != 4:
        return False
    if not 0 <= q.correct_index <= 3:
        return False
    if len(q.question.strip()) < 10:
        return False
    lowered = " ".join(opts).lower()
    return "all of the above" not in lowered and "none of the above" not in lowered


def shuffle_options(options: list[str], correct_index: int, rng: random.Random) -> tuple[list[str], int]:
    """Models like putting the right answer in the same slot; shuffle so position carries no signal."""
    order = list(range(4))
    rng.shuffle(order)
    return [options[i] for i in order], order.index(correct_index)


def generate_for_section(
    section: Section, chapter_title: str, count: int, rng: random.Random
) -> list[RawQuestion]:
    if count <= 0:
        return []
    user = f"Chapter: {chapter_title}\n\nPassage:\n{section.text}"
    batch = generate_json(SYSTEM.format(count=count), user, _QuizBatch)
    if batch is None:
        log.warning("No valid questions for chapter %s section %s", section.chapter_idx, section.idx)
        return []
    out: list[RawQuestion] = []
    for q in batch.questions:
        if not validate(q):
            continue
        options, correct = shuffle_options([o.strip() for o in q.options], q.correct_index, rng)
        out.append(
            RawQuestion(
                chapter_idx=section.chapter_idx,
                question=strip_passage_references(q.question.strip()),
                options=options,
                correct_index=correct,
                explanation=q.explanation.strip(),
                page=section.page_start,
            )
        )
    return out
