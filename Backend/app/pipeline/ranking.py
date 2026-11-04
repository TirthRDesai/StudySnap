"""Rank the full flashcard pool and pick the top N for the whole book.

score = blend of
  - the model's importance rating, as a percentile within its chapter (ratings are only
    calibrated inside one section, so they are not compared raw across chapters),
  - centrality: similarity of the card to its chapter's centroid,
  - key-term overlap with the chapter's most frequent terms and title,
  - (exam mode) a bonus for card types that tend to be tested.
Selection uses MMR so near-duplicates and tight clusters don't crowd out other topics, with a
per-chapter quota proportional to chapter length so no chapter is dropped.
"""
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

DUPLICATE_SIM = 0.90
MMR_LAMBDA = 0.7
KEYWORD_COUNT = 40

TESTED_TYPES = {"definition", "formula", "comparison", "cause_effect", "process"}

WEIGHTS = {
    # llm, centrality, terms, type bonus
    "exam": (0.50, 0.20, 0.20, 0.10),
    "overview": (0.35, 0.40, 0.25, 0.00),
}

_STOP = set(
    """a about above after again all also an and any are as at be because been before being below between both but by
    can could did do does doing down during each few for from further had has have having he her here hers him his how
    i if in into is it its itself just me more most my no nor not of off on once only or other our out over own same she
    should so some such than that the their theirs them then there these they this those through to too under until up
    very was we were what when where which while who whom why will with would you your may might must shall one two three
    use used using new many much like make made""".split()
)
_TOKEN_RE = re.compile(r"[a-z][a-z'\-]{2,}")


@dataclass
class Card:
    chapter_idx: int
    front: str
    back: str
    card_type: str
    importance: int
    page: int
    fmt: str = "qa"
    options: list[str] | None = None
    embedding: np.ndarray | None = None
    score: float = 0.0
    rank: int = 0
    selected: bool = False
    _parts: dict[str, float] = field(default_factory=dict, repr=False)


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def allocate(total: int, weights: list[float], floor: int = 0) -> list[int]:
    """Split `total` across buckets proportionally to `weights` (largest remainder), each >= floor."""
    k = len(weights)
    if k == 0:
        return []
    if floor * k > total:
        floor = total // k
    remaining = total - floor * k
    wsum = sum(weights) or float(k)
    norm = [w / wsum if sum(weights) else 1 / k for w in weights]
    raw = [remaining * w for w in norm]
    ints = [int(x) for x in raw]
    order = sorted(range(k), key=lambda i: raw[i] - ints[i], reverse=True)
    for i in order[: remaining - sum(ints)]:
        ints[i] += 1
    return [floor + x for x in ints]


def _percentiles(values: list[float]) -> list[float]:
    n = len(values)
    return [
        (sum(1 for o in values if o < v) + 0.5 * sum(1 for o in values if o == v)) / n for v in values
    ]


def _minmax(values: np.ndarray) -> np.ndarray:
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-9:
        return np.full_like(values, 0.5, dtype=float)
    return (values - lo) / (hi - lo)


def chapter_keywords(text: str, title: str) -> set[str]:
    counts = Counter(tokens(text))
    keywords = {w for w, _ in counts.most_common(KEYWORD_COUNT)}
    keywords.update(tokens(title))
    return keywords


def score_cards(
    cards: list[Card], chapter_text: dict[int, str], chapter_title: dict[int, str], mode: str
) -> None:
    w_llm, w_cent, w_terms, w_type = WEIGHTS.get(mode, WEIGHTS["exam"])
    by_chapter: dict[int, list[Card]] = {}
    for c in cards:
        by_chapter.setdefault(c.chapter_idx, []).append(c)

    for ch, group in by_chapter.items():
        llm_pct = _percentiles([float(c.importance) for c in group])

        emb = np.vstack([c.embedding for c in group])
        centroid = emb.mean(axis=0)
        norm = np.linalg.norm(centroid)
        sims = emb @ (centroid / norm) if norm > 0 else np.zeros(len(group))
        central = _minmax(np.asarray(sims, dtype=float))

        keywords = chapter_keywords(chapter_text.get(ch, ""), chapter_title.get(ch, ""))
        for i, c in enumerate(group):
            toks = set(tokens(c.front + " " + c.back))
            terms = min(1.0, 2.5 * len(toks & keywords) / len(toks)) if toks else 0.0
            type_bonus = 1.0 if c.card_type in TESTED_TYPES else 0.4
            c._parts = {"llm": llm_pct[i], "central": float(central[i]), "terms": terms, "type": type_bonus}
            c.score = float(w_llm * llm_pct[i] + w_cent * central[i] + w_terms * terms + w_type * type_bonus)


def _mmr_pick(pool: list[Card], chosen: list[Card], want: int, global_chosen: list[Card]) -> list[Card]:
    """Greedy MMR selection of up to `want` cards from `pool`, avoiding near-duplicates of any chosen card."""
    picked: list[Card] = []
    candidates = sorted(pool, key=lambda c: c.score, reverse=True)
    while candidates and len(picked) < want:
        reference = chosen + picked + global_chosen
        best, best_val = None, -1e9
        survivors: list[Card] = []
        for c in candidates:
            max_sim = max((float(c.embedding @ r.embedding) for r in reference), default=0.0)
            if max_sim >= DUPLICATE_SIM:
                continue  # near-duplicate of something already kept
            survivors.append(c)
            val = MMR_LAMBDA * c.score - (1 - MMR_LAMBDA) * max_sim
            if val > best_val:
                best, best_val = c, val
        candidates = survivors
        if best is None:
            break
        picked.append(best)
        candidates.remove(best)
    return picked


def select_top_n(cards: list[Card], chapter_words: dict[int, int], n: int) -> None:
    """Mark the best `n` cards as selected and assign `rank` (1 = best) to the whole pool."""
    chapters = sorted({c.chapter_idx for c in cards})
    floor = 2 if n >= 2 * len(chapters) else (1 if n >= len(chapters) else 0)
    quotas = allocate(n, [float(chapter_words.get(ch, 1)) for ch in chapters], floor)

    selected: list[Card] = []
    for ch, quota in zip(chapters, quotas):
        group = [c for c in cards if c.chapter_idx == ch]
        selected.extend(_mmr_pick(group, [], quota, list(selected)))

    # chapters with fewer good cards than their quota leave room: fill from the best of the rest
    if len(selected) < n:
        taken = {id(c) for c in selected}
        rest = [c for c in cards if id(c) not in taken]
        selected.extend(_mmr_pick(rest, selected, n - len(selected), []))

    for c in cards:
        c.selected = False
    for c in selected:
        c.selected = True

    ordered = sorted(selected, key=lambda c: c.score, reverse=True)
    ordered += sorted((c for c in cards if not c.selected), key=lambda c: c.score, reverse=True)
    for i, c in enumerate(ordered, start=1):
        c.rank = i


def normalize(vectors: list[list[float]]) -> list[np.ndarray]:
    out = []
    for v in vectors:
        a = np.asarray(v, dtype=float)
        n = np.linalg.norm(a)
        out.append(a / n if n > 0 else a)
    return out


def dedupe_by_embedding(items_embeddings: list[np.ndarray], threshold: float = DUPLICATE_SIM) -> list[int]:
    """Indices to keep, in order, dropping items too similar to an earlier kept item."""
    kept: list[int] = []
    for i, e in enumerate(items_embeddings):
        if all(float(e @ items_embeddings[j]) < threshold for j in kept):
            kept.append(i)
    return kept
