from pathlib import Path

from app.services.parsers.epub import parse_epub
from app.services.parsers.gz import parse_gz
from app.services.parsers.html import parse_html
from app.services.parsers.md import parse_md
from app.services.parsers.txt import parse_txt


def parse_source_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return parse_txt(path)
    if ext == ".md":
        return parse_md(path)
    if ext == ".html":
        return parse_html(path)
    if ext == ".epub":
        return parse_epub(path)
    if ext == ".gz":
        return parse_gz(path)
    raise ValueError(f"Unsupported extension: {ext}")

