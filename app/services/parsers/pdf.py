from pathlib import Path

from pypdf import PdfReader


def parse_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text.strip())
    merged = "\n\n".join(parts).strip()
    if not merged:
        raise ValueError("PDF contains no extractable digital text")
    return merged
