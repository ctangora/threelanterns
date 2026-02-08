import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path


def now_utc() -> datetime:
    return datetime.now(UTC)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_to_english(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact


def split_into_passages(text: str, minimum_length: int = 180) -> list[str]:
    raw_chunks = re.split(r"\n{2,}", text)
    passages: list[str] = []
    for chunk in raw_chunks:
        compact = re.sub(r"\s+", " ", chunk).strip()
        if len(compact) >= minimum_length:
            passages.append(compact)
    if not passages:
        fallback = re.sub(r"\s+", " ", text).strip()
        if fallback:
            passages.append(fallback[:2000])
    return passages


def guess_language_code(text: str) -> str:
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / max(len(text), 1)
    if ascii_ratio > 0.95:
        return "eng"
    return "und"

