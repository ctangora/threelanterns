from pathlib import Path


def parse_txt(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_txt_garble(path: Path) -> str:
    data = parse_txt(path)
    cleaned = "".join(char if char.isprintable() or char in {"\n", "\t"} else " " for char in data)
    cleaned = cleaned.replace("\ufffd", " ").replace("�", " ")
    return cleaned
