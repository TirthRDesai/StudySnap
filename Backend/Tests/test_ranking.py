import numpy as np

from app.pipeline.ranking import (
    Card,
    allocate,
    dedupe_by_embedding,
    normalize,
    score_cards,
    select_top_n,
)


def _unit(*xs: float) -> np.ndarray:
    return normalize([list(xs)])[0]


def test_allocate_sums_to_total_and_respects_floor():
    out = allocate(10, [100, 50, 10, 1], floor=1)
    assert sum(out) == 10
    assert all(x >= 1 for x in out)
    assert out[0] >= out[1] >= out[2]


def test_allocate_floor_too_big_falls_back():
    out = allocate(3, [1, 1, 1, 1, 1], floor=2)
    assert sum(out) == 3


def test_allocate_zero_weights_is_even():
    assert sum(allocate(9, [0, 0, 0])) == 9


def test_dedupe_drops_near_duplicates():
    vecs = [_unit(1, 0, 0), _unit(1, 0.01, 0), _unit(0, 1, 0)]
    assert dedupe_by_embedding(vecs) == [0, 2]


def _cards() -> list[Card]:
    rng = np.random.default_rng(0)
    cards = []
    for ch in range(3):
        for i in range(8):
            v = normalize([rng.normal(size=16).tolist()])[0]
            cards.append(Card(ch, f"Q{ch}-{i}", f"A{ch}-{i}", "definition" if i % 2 else "fact",
                              importance=1 + (i % 5), page=ch * 10 + i, embedding=v))
    return cards


def test_select_top_n_picks_exactly_n_and_covers_every_chapter():
    cards = _cards()
    score_cards(cards, {0: "alpha beta", 1: "gamma", 2: "delta"}, {0: "A", 1: "B", 2: "C"}, "exam")
    select_top_n(cards, {0: 1000, 1: 1000, 2: 1000}, n=9)
    chosen = [c for c in cards if c.selected]
    assert len(chosen) == 9
    assert {c.chapter_idx for c in chosen} == {0, 1, 2}


def test_ranks_are_a_permutation_with_selected_first():
    cards = _cards()
    score_cards(cards, {}, {}, "overview")
    select_top_n(cards, {0: 10, 1: 10, 2: 10}, n=6)
    assert sorted(c.rank for c in cards) == list(range(1, len(cards) + 1))
    assert max(c.rank for c in cards if c.selected) <= 6


def test_longer_chapters_get_more_cards():
    cards = _cards()
    score_cards(cards, {}, {}, "exam")
    select_top_n(cards, {0: 9000, 1: 1000, 2: 1000}, n=8)
    per = [sum(c.selected for c in cards if c.chapter_idx == ch) for ch in range(3)]
    assert per[0] > per[1]


def test_near_duplicate_cards_are_not_both_selected():
    base = _unit(1, 0, 0, 0)
    cards = [
        Card(0, "same?", "a", "definition", 5, 1, embedding=base),
        Card(0, "same??", "a", "definition", 5, 1, embedding=_unit(1, 0.001, 0, 0)),
        Card(0, "other", "b", "definition", 3, 1, embedding=_unit(0, 1, 0, 0)),
    ]
    score_cards(cards, {}, {}, "exam")
    select_top_n(cards, {0: 100}, n=3)
    assert sum(c.selected for c in cards) == 2


def test_fewer_cards_than_n_selects_all_unique():
    cards = _cards()[:5]
    score_cards(cards, {}, {}, "exam")
    select_top_n(cards, {0: 10}, n=50)
    assert all(c.selected for c in cards)
