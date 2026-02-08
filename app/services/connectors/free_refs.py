from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class FreeReferenceCandidate:
    provider: str
    title: str
    locator: str
    snippet: str
    score: float
    metadata: dict[str, Any]


def _score(query_title: str, query_snippet: str, *, title: str, snippet: str) -> float:
    target = f"{title} {snippet}".lower()
    query = f"{query_title} {query_snippet}".lower()
    if not target.strip():
        return 0.0
    ratio = SequenceMatcher(None, query[:1200], target[:1200]).ratio()
    return round(ratio, 4)


def _fetch_json(url: str, *, timeout: int = 8) -> dict[str, Any] | list[Any] | None:
    request = Request(url, headers={"User-Agent": "three-lanterns/0.3"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _search_wikisource(title: str, snippet: str, *, limit: int, timeout: int) -> list[FreeReferenceCandidate]:
    params = urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": f"{title} {snippet[:160]}",
            "format": "json",
            "utf8": "1",
            "srlimit": str(limit),
        }
    )
    payload = _fetch_json(f"https://en.wikisource.org/w/api.php?{params}", timeout=timeout)
    if not isinstance(payload, dict):
        return []
    items = payload.get("query", {}).get("search", [])
    if not isinstance(items, list):
        return []
    candidates: list[FreeReferenceCandidate] = []
    for item in items:
        page_title = str(item.get("title") or "").strip()
        if not page_title:
            continue
        page_snippet = str(item.get("snippet") or "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
        locator = f"https://en.wikisource.org/wiki/{page_title.replace(' ', '_')}"
        candidates.append(
            FreeReferenceCandidate(
                provider="wikisource",
                title=page_title,
                locator=locator,
                snippet=page_snippet,
                score=_score(title, snippet, title=page_title, snippet=page_snippet),
                metadata={"pageid": item.get("pageid")},
            )
        )
    return candidates


def _search_internet_archive(title: str, snippet: str, *, limit: int, timeout: int) -> list[FreeReferenceCandidate]:
    query = f"title:({title}) AND mediatype:texts"
    params = urlencode(
        {
            "q": query,
            "fl[]": ["identifier", "title", "description"],
            "rows": str(limit),
            "page": "1",
            "output": "json",
        },
        doseq=True,
    )
    payload = _fetch_json(f"https://archive.org/advancedsearch.php?{params}", timeout=timeout)
    if not isinstance(payload, dict):
        return []
    docs = payload.get("response", {}).get("docs", [])
    if not isinstance(docs, list):
        return []
    candidates: list[FreeReferenceCandidate] = []
    for item in docs:
        identifier = str(item.get("identifier") or "").strip()
        page_title = str(item.get("title") or identifier).strip()
        if not identifier:
            continue
        raw_description = item.get("description")
        description = raw_description[0] if isinstance(raw_description, list) and raw_description else raw_description
        page_snippet = str(description or "")[:400]
        locator = f"https://archive.org/details/{identifier}"
        candidates.append(
            FreeReferenceCandidate(
                provider="internet_archive",
                title=page_title,
                locator=locator,
                snippet=page_snippet,
                score=_score(title, snippet, title=page_title, snippet=page_snippet),
                metadata={"identifier": identifier},
            )
        )
    return candidates


def _search_gutendex(title: str, snippet: str, *, limit: int, timeout: int) -> list[FreeReferenceCandidate]:
    params = urlencode({"search": title})
    payload = _fetch_json(f"https://gutendex.com/books?{params}", timeout=timeout)
    if not isinstance(payload, dict):
        return []
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    candidates: list[FreeReferenceCandidate] = []
    for item in results[:limit]:
        page_title = str(item.get("title") or "").strip()
        if not page_title:
            continue
        languages = item.get("languages") if isinstance(item.get("languages"), list) else []
        page_snippet = f"languages={','.join(str(lang) for lang in languages)}"
        book_id = str(item.get("id") or "").strip()
        locator = f"https://www.gutenberg.org/ebooks/{book_id}" if book_id else "https://www.gutenberg.org/"
        candidates.append(
            FreeReferenceCandidate(
                provider="gutenberg",
                title=page_title,
                locator=locator,
                snippet=page_snippet,
                score=_score(title, snippet, title=page_title, snippet=page_snippet),
                metadata={"book_id": book_id, "languages": languages},
            )
        )
    return candidates


def search_free_references(title: str, snippet: str, *, limit: int = 5, timeout: int = 8) -> list[FreeReferenceCandidate]:
    candidates: list[FreeReferenceCandidate] = []
    candidates.extend(_search_wikisource(title, snippet, limit=limit, timeout=timeout))
    candidates.extend(_search_internet_archive(title, snippet, limit=limit, timeout=timeout))
    candidates.extend(_search_gutendex(title, snippet, limit=limit, timeout=timeout))

    deduped: dict[tuple[str, str], FreeReferenceCandidate] = {}
    for candidate in candidates:
        key = (candidate.provider, candidate.locator)
        existing = deduped.get(key)
        if existing is None or candidate.score > existing.score:
            deduped[key] = candidate

    ranked = sorted(deduped.values(), key=lambda item: (-item.score, item.provider, item.title))
    return ranked[: max(1, limit)]
