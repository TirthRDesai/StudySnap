import random

from app.pipeline.flashcards import _CardOut, _finish, _valid


def _card(front, back="An answer.", fmt="qa", options=None):
    return _CardOut(front=front, back=back, type="concept", format=fmt, options=options or [], importance=3)


def test_qa_rejects_bare_topic_titles():
    assert not _valid(_card("Definition of an Algorithm"))
    assert not _valid(_card("Input and Output in Algorithms"))


def test_qa_accepts_questions_and_instructions():
    assert _valid(_card("What does it mean for an algorithm to halt?"))
    assert _valid(_card("Define an algorithm."))
    assert _valid(_card("Explain why sorting is needed"))


def test_cloze_needs_exactly_one_blank():
    assert _valid(_card("An _____ is a step-by-step procedure.", "algorithm", "cloze"))
    assert not _valid(_card("An algorithm is a procedure.", "algorithm", "cloze"))
    assert not _valid(_card("An _____ is a _____ procedure.", "algorithm", "cloze"))


def test_true_false_answer_must_start_with_the_verdict():
    assert _valid(_card("Every algorithm halts.", "False. Some run forever.", "true_false"))
    assert not _valid(_card("Every algorithm halts.", "Some run forever.", "true_false"))
    front, _, _ = _finish(_card("Every algorithm halts.", "False. Some run forever.", "true_false"), random.Random(0))
    assert front.startswith("True or false:")


def test_true_false_prefix_is_not_doubled():
    card = _card("True or false: Every algorithm halts.", "False. Some run forever.", "true_false")
    front, _, _ = _finish(card, random.Random(0))
    assert front == "True or false: Every algorithm halts."


def test_mcq_needs_four_distinct_choices_and_a_question():
    good = _card("What is an algorithm?", "It is a procedure.", "mcq", ["A procedure", "A language", "A chip", "A bug"])
    assert _valid(good)
    assert not _valid(_card("What is an algorithm?", "x", "mcq", ["A", "a", "B", "C"]))
    assert not _valid(_card("What is an algorithm?", "x", "mcq", ["A", "B", "C", "All of the above"]))
    assert not _valid(_card("Pick one", "x", "mcq", ["A", "B", "C", "D"]))


def test_mcq_shuffle_names_the_correct_letter():
    card = _card("What is an algorithm?", "It is a procedure.", "mcq", ["A procedure", "A language", "A chip", "A bug"])
    front, back, options = _finish(card, random.Random(1))
    assert sorted(options) == ["A bug", "A chip", "A language", "A procedure"]
    letter = back[0]
    assert options["ABCD".index(letter)] == "A procedure"
