from pathlib import Path

from docx import Document


def parse_docx(path: Path) -> str:
    document = Document(str(path))
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text and paragraph.text.strip()]
    merged = "\n\n".join(parts).strip()
    if not merged:
        raise ValueError("DOCX contains no extractable text")
    return merged
