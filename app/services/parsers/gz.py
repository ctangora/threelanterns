import gzip
from pathlib import Path


def parse_gz(path: Path) -> str:
    with gzip.open(path, "rb") as handle:
        data = handle.read()
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

