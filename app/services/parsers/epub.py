from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub


def parse_epub(path: Path) -> str:
    book = epub.read_epub(str(path))
    chunks: list[str] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_body_content(), "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)

