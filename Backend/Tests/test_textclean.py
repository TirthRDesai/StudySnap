import pytest

from app.pipeline.textclean import strip_passage_references as clean


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("What is the primary goal of the Visual Dialog task as described in the passage?",
         "What is the primary goal of the Visual Dialog task?"),
        ("What is the main contribution of the RVA model according to the passage?",
         "What is the main contribution of the RVA model?"),
        ("According to the text, what causes inflation?", "What causes inflation?"),
        ("What is a mitochondrion?", "What is a mitochondrion?"),
        ("Define entropy.", "Define entropy."),
    ],
)
def test_strip_passage_references(raw, expected):
    assert clean(raw) == expected
