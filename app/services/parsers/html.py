from pathlib import Path

from bs4 import BeautifulSoup

from app.services.parsers.txt import parse_txt


def parse_html(path: Path) -> str:
    html = parse_txt(path)
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)

