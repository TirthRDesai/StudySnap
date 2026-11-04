from pathlib import Path

import pytest

from app.pipeline.extract import ExtractionError, extract_book, looks_like_pdf

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("pdf", sorted(FIXTURES.glob("*.pdf")), ids=lambda p: p.name)
def test_fixture_books_extract_into_ordered_chapters(pdf: Path):
    book = extract_book(pdf.read_bytes())
    assert book.page_count > 0
    assert book.chapters
    assert [c.idx for c in book.chapters] == list(range(len(book.chapters)))
    starts = [c.page_start for c in book.chapters]
    assert starts == sorted(starts)
    assert book.word_count > 300


def test_rejects_non_pdf_bytes():
    assert not looks_like_pdf(b"hello world")
    with pytest.raises(ExtractionError):
        extract_book(b"hello world")


def test_pdf_magic_bytes():
    assert looks_like_pdf(b"%PDF-1.7 ...")
