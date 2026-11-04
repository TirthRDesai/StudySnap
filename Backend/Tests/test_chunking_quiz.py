import random

from app.pipeline.chunking import MAX_SECTION_WORDS, split_chapter
from app.pipeline.extract import Chapter
from app.pipeline import quiz


def _chapter(words_per_page: int, pages: int) -> Chapter:
    body = " ".join(f"word{i}." if i % 12 == 11 else f"word{i}" for i in range(words_per_page))
    return Chapter(0, "Ch", 1, pages, pages=[(p + 1, body) for p in range(pages)])


def test_sections_stay_under_the_word_limit_and_keep_all_text():
    ch = _chapter(900, 8)
    sections = split_chapter(ch)
    assert len(sections) > 1
    assert all(s.word_count <= MAX_SECTION_WORDS + 250 for s in sections)
    assert sum(s.word_count for s in sections) == ch.word_count


def test_section_pages_are_ordered_and_in_range():
    sections = split_chapter(_chapter(900, 8))
    for s in sections:
        assert 1 <= s.page_start <= s.page_end <= 8
    assert [s.idx for s in sections] == list(range(len(sections)))


def test_single_huge_paragraph_is_split_by_sentences():
    text = " ".join(f"This is sentence number {i} of a very long paragraph." for i in range(600))
    ch = Chapter(0, "Ch", 1, 1, pages=[(1, text)])
    assert len(split_chapter(ch)) > 1


def _q(options, idx=0, question="What is the powerhouse of the cell?"):
    return quiz._QuestionOut(question=question, options=options, correct_index=idx, explanation="Because.")


def test_validate_accepts_good_question():
    assert quiz.validate(_q(["Mitochondria", "Nucleus", "Ribosome", "Golgi body"]))


def test_validate_rejects_bad_questions():
    assert not quiz.validate(_q(["A", "B", "C"]))  # wrong option count
    assert not quiz.validate(_q(["A", "a", "C", "D"]))  # duplicate options
    assert not quiz.validate(_q(["A", "B", "C", "All of the above"]))
    assert not quiz.validate(_q(["A", "B", "C", "D"], idx=4))
    assert not quiz.validate(_q(["A", "B", "C", ""]))


def test_shuffle_keeps_the_correct_answer_correct():
    rng = random.Random(1)
    opts = ["right", "x", "y", "z"]
    positions = set()
    for _ in range(40):
        shuffled, idx = quiz.shuffle_options(opts, 0, rng)
        assert shuffled[idx] == "right"
        assert sorted(shuffled) == sorted(opts)
        positions.add(idx)
    assert len(positions) > 1


def test_question_counts_are_capped_per_section():
    counts = quiz.question_counts(100, [1.0, 1.0])
    assert all(c <= quiz.MAX_QUESTIONS_PER_SECTION for c in counts)
