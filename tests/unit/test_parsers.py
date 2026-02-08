import gzip

import pytest

from app.services.parsers import parse_source_file


def test_parser_txt(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("hello ritual world", encoding="utf-8")
    assert "ritual" in parse_source_file(path)


def test_parser_md(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# Heading\n\nritual notes", encoding="utf-8")
    assert "ritual notes" in parse_source_file(path)


def test_parser_html(tmp_path):
    path = tmp_path / "sample.html"
    path.write_text("<html><body><h1>Ritual</h1><p>text</p></body></html>", encoding="utf-8")
    parsed = parse_source_file(path)
    assert "Ritual" in parsed
    assert "text" in parsed


def test_parser_gz(tmp_path):
    path = tmp_path / "sample.txt.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(b"compressed ritual text")
    assert "compressed ritual text" in parse_source_file(path)


def test_parser_epub(tmp_path):
    pytest.importorskip("ebooklib")
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id123")
    book.set_title("sample")
    c1 = epub.EpubHtml(title="intro", file_name="chap_01.xhtml", lang="en")
    c1.content = "<h1>Ritual</h1><p>epub body</p>"
    book.add_item(c1)
    book.toc = (epub.Link("chap_01.xhtml", "Intro", "intro"),)
    book.spine = ["nav", c1]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    path = tmp_path / "sample.epub"
    epub.write_epub(str(path), book)
    parsed = parse_source_file(path)
    assert "Ritual" in parsed
