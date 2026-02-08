import gzip
from pathlib import Path

import pytest
from docx import Document

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


def test_parser_docx(tmp_path):
    path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("Ritual document text")
    document.save(path)
    parsed = parse_source_file(path)
    assert "Ritual document text" in parsed


def test_parser_rtf(tmp_path):
    path = tmp_path / "sample.rtf"
    path.write_text(r"{\rtf1\ansi Ritual RTF text}", encoding="utf-8")
    parsed = parse_source_file(path)
    assert "Ritual RTF text" in parsed


def test_parser_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    _write_minimal_text_pdf(path, text="Ritual PDF text")
    parsed = parse_source_file(path)
    assert "Ritual PDF text" in parsed


def _write_minimal_text_pdf(path: Path, *, text: str) -> None:
    stream = f"BT /F1 18 Tf 50 90 Td ({text}) Tj ET"
    encoded_stream = stream.encode("utf-8")
    header = "%PDF-1.4\n"
    objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(encoded_stream)} >>\nstream\n{stream}\nendstream\nendobj\n",
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    content = header
    offsets = [0]
    for obj in objects:
        offsets.append(len(content.encode("utf-8")))
        content += obj

    xref_start = len(content.encode("utf-8"))
    xref = ["xref\n0 6\n0000000000 65535 f \n"]
    for index in range(1, 6):
        xref.append(f"{offsets[index]:010d} 00000 n \n")
    trailer = "trailer\n<< /Size 6 /Root 1 0 R >>\n"
    startxref = f"startxref\n{xref_start}\n%%EOF\n"
    content += "".join(xref) + trailer + startxref
    path.write_bytes(content.encode("utf-8"))
