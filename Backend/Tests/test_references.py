from app.pipeline.extract import Chapter, _drop_references


def _chapter(idx: int, pages: list[str]) -> Chapter:
    return Chapter(idx, f"Ch{idx}", 1, len(pages), pages=[(i + 1, t) for i, t in enumerate(pages)])


def test_text_after_references_heading_is_dropped():
    ch = _chapter(0, ["Intro text here.", "More body text.\nReferences\n[1] Foo. Bar. 2020.", "[2] Baz. Qux. 2021."])
    out = _drop_references([ch])
    assert len(out) == 1
    text = " ".join(t for _, t in out[0].pages)
    assert "More body text." in text
    assert "Foo" not in text and "Baz" not in text
    assert out[0].page_end == 2


def test_numbered_bibliography_heading_matches():
    out = _drop_references([_chapter(0, ["Body.\n7. Bibliography\n[1] Foo."])])
    assert " ".join(t for _, t in out[0].pages) == "Body."


def test_heading_must_stand_alone_on_its_line():
    ch = _chapter(0, ["See the references section for details.\nReferences to the past are common."])
    out = _drop_references([ch])
    assert len(out[0].pages) == 1 and "common" in out[0].pages[0][1]


def test_chapter_that_is_only_references_is_removed_and_reindexed():
    chapters = [_chapter(0, ["Real content."]), _chapter(1, ["References\n[1] Foo."]), _chapter(2, ["More content."])]
    out = _drop_references(chapters)
    assert [c.idx for c in out] == [0, 1]
    assert [c.pages[0][1] for c in out] == ["Real content.", "More content."]
