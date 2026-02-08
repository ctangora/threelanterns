from pathlib import Path

from striprtf.striprtf import rtf_to_text


def parse_rtf(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    parsed = rtf_to_text(raw).strip()
    if not parsed:
        raise ValueError("RTF contains no extractable text")
    return parsed
