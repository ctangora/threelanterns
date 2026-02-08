from pathlib import Path

from app.services.parsers.docx import parse_docx
from app.services.parsers.epub import parse_epub
from app.services.parsers.gz import parse_gz
from app.services.parsers.html import parse_html
from app.services.parsers.md import parse_md
from app.services.parsers.pdf import parse_pdf
from app.services.parsers.rtf import parse_rtf
from app.services.parsers.txt import parse_txt, parse_txt_garble


def parse_source_file(path: Path) -> str:
    return parse_source_file_with_metadata(path)["text"]


def parse_source_file_with_metadata(path: Path, *, parser_strategy: str | None = None) -> dict[str, str]:
    ext = path.suffix.lower()
    strategy = (parser_strategy or "auto_by_extension").strip() or "auto_by_extension"
    if ext == ".txt":
        if strategy == "txt:garble_v1":
            return {"text": parse_txt_garble(path), "parser_name": "txt", "parser_version": "garble_v1", "parser_strategy": strategy}
        if strategy in {"auto_by_extension", "txt:clean_v1"}:
            return {"text": parse_txt(path), "parser_name": "txt", "parser_version": "v1", "parser_strategy": strategy}
        return {"text": parse_txt(path), "parser_name": "txt", "parser_version": "v1", "parser_strategy": strategy}
    if ext == ".md":
        return {"text": parse_md(path), "parser_name": "md", "parser_version": "v1", "parser_strategy": strategy}
    if ext == ".html":
        return {"text": parse_html(path), "parser_name": "html", "parser_version": "v1", "parser_strategy": strategy}
    if ext == ".epub":
        return {"text": parse_epub(path), "parser_name": "epub", "parser_version": "v1", "parser_strategy": strategy}
    if ext == ".gz":
        return {"text": parse_gz(path), "parser_name": "gz", "parser_version": "v1", "parser_strategy": strategy}
    if ext == ".pdf":
        return {"text": parse_pdf(path), "parser_name": "pdf", "parser_version": "v1", "parser_strategy": strategy}
    if ext == ".docx":
        return {"text": parse_docx(path), "parser_name": "docx", "parser_version": "v1", "parser_strategy": strategy}
    if ext == ".rtf":
        return {"text": parse_rtf(path), "parser_name": "rtf", "parser_version": "v1", "parser_strategy": strategy}
    raise ValueError(f"Unsupported extension: {ext}")
