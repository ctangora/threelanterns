from pathlib import Path

from app.services.parsers.txt import parse_txt


def parse_md(path: Path) -> str:
    return parse_txt(path)

