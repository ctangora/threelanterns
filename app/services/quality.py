from __future__ import annotations

from dataclasses import dataclass
import re

from app.constants import (
    ONTOLOGY_DIMENSIONS,
    PASSAGE_QUALITY_VERSION,
    PASSAGE_RELEVANCE_ACCEPT_THRESHOLD,
    PASSAGE_RELEVANCE_FILTER_THRESHOLD,
    TRADITION_VOCABULARY,
)
from app.enums import RelevanceState

_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
_PUNCT_PATTERN = re.compile(r"[^\w\s]")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NOISY_SYMBOL_PATTERN = re.compile(r"[^\w\s\.,;:!?\"'()\-\n]")
_SYMBOL_CLUSTER_PATTERN = re.compile(r"[^\w\s]{3,}")

_RITUAL_KEYWORDS = {
    "ritual",
    "magic",
    "magical",
    "mystic",
    "mysticism",
    "pagan",
    "occult",
    "esoteric",
    "incantation",
    "invocation",
    "offering",
    "libation",
    "divination",
    "sigil",
    "amulet",
    "altar",
    "ceremony",
    "prayer",
    "spell",
    "curse",
    "blessing",
    "oracle",
    "deity",
    "ancestor",
    "spirit",
    "temple",
    "sanctuary",
    "liturgy",
    "recitation",
    "anointing",
    "consecrate",
    "apotropaic",
    "votive",
}

_NEGATIVE_NOISE_KEYWORDS = {
    "table",
    "contents",
    "index",
    "chapter",
    "copyright",
    "isbn",
    "navigation",
    "header",
    "footer",
    "advertisement",
    "appendix",
    "preface",
    "publisher",
    "project",
    "gutenberg",
    "http",
    "www",
    "click",
    "download",
    "menu",
    "breadcrumb",
    "sidebar",
}

_NEGATIVE_NOISE_PHRASES = {
    "table of contents",
    "all rights reserved",
    "project gutenberg",
    "chapter one",
    "chapter 1",
    "page number",
    "copyright notice",
    "navigation menu",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


def _build_ontology_lexicon() -> set[str]:
    lexicon: set[str] = set()
    for dimension_terms in ONTOLOGY_DIMENSIONS.values():
        for term in dimension_terms:
            lexicon.update(part for part in term.lower().split("_") if part)
    for tag in TRADITION_VOCABULARY:
        lexicon.update(part for part in tag.lower().split("_") if part)
    return lexicon


_ONTOLOGY_LEXICON = _build_ontology_lexicon()
_POSITIVE_LEXICON = _ONTOLOGY_LEXICON.union(_RITUAL_KEYWORDS)


@dataclass(frozen=True)
class QualityConfig:
    relevance_accept_threshold: float = PASSAGE_RELEVANCE_ACCEPT_THRESHOLD
    relevance_filter_threshold: float = PASSAGE_RELEVANCE_FILTER_THRESHOLD
    quality_version: str = PASSAGE_QUALITY_VERSION
    positive_keywords: set[str] = None  # type: ignore[assignment]
    noise_keywords: set[str] = None  # type: ignore[assignment]
    noise_phrases: set[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:  # pragma: no cover
        if self.positive_keywords is None:
            object.__setattr__(self, "positive_keywords", set(_POSITIVE_LEXICON))
        if self.noise_keywords is None:
            object.__setattr__(self, "noise_keywords", set(_NEGATIVE_NOISE_KEYWORDS))
        if self.noise_phrases is None:
            object.__setattr__(self, "noise_phrases", set(_NEGATIVE_NOISE_PHRASES))


DEFAULT_QUALITY_CONFIG = QualityConfig()


@dataclass
class PassageQualityAssessment:
    usability_score: float
    relevance_score: float
    relevance_state: RelevanceState
    notes: dict
    quality_version: str = PASSAGE_QUALITY_VERSION


def score_usability(text: str) -> tuple[float, dict]:
    if not text:
        return 0.0, {
            "printable_ratio": 0.0,
            "alpha_token_ratio": 0.0,
            "digit_token_ratio": 0.0,
            "replacement_ratio": 1.0,
            "noisy_symbol_ratio": 1.0,
            "symbol_cluster_ratio": 1.0,
            "repetition_ratio": 1.0,
            "punctuation_ratio": 1.0,
            "average_word_length": 0.0,
            "subscores": {},
        }

    length = max(len(text), 1)
    tokens = _tokenize(text)
    total_tokens = max(len(tokens), 1)

    printable_ratio = sum(1 for char in text if char.isprintable()) / length
    control_ratio = len(_CONTROL_PATTERN.findall(text)) / length
    replacement_ratio = (text.count("\ufffd") + text.count("�")) / length
    alpha_token_ratio = sum(1 for token in tokens if any(char.isalpha() for char in token)) / total_tokens
    digit_token_ratio = sum(1 for token in tokens if token.isdigit()) / total_tokens
    unique_ratio = len(set(tokens)) / total_tokens
    repetition_ratio = 1.0 - unique_ratio
    punctuation_ratio = len(_PUNCT_PATTERN.findall(text)) / length
    noisy_symbol_ratio = len(_NOISY_SYMBOL_PATTERN.findall(text)) / length
    symbol_cluster_chars = sum(len(match.group(0)) for match in _SYMBOL_CLUSTER_PATTERN.finditer(text))
    symbol_cluster_ratio = symbol_cluster_chars / length
    average_word_length = sum(len(token) for token in tokens) / total_tokens

    printable_score = _clamp((printable_ratio - 0.85) / 0.15)
    control_score = _clamp(1.0 - (control_ratio / 0.02))
    replacement_score = _clamp(1.0 - (replacement_ratio / 0.03))
    alpha_score = _clamp((alpha_token_ratio - 0.45) / 0.55)
    digit_score = _clamp(1.0 - (digit_token_ratio / 0.12))
    repetition_score = _clamp((unique_ratio - 0.18) / 0.82)
    punctuation_score = _clamp(1.0 - (punctuation_ratio / 0.28))
    noisy_symbol_score = _clamp(1.0 - (noisy_symbol_ratio / 0.04))
    symbol_cluster_score = _clamp(1.0 - (symbol_cluster_ratio / 0.06))
    word_length_score = _clamp(1.0 - (abs(average_word_length - 6.0) / 8.0))

    weighted = (
        printable_score * 0.12
        + control_score * 0.08
        + replacement_score * 0.12
        + alpha_score * 0.12
        + digit_score * 0.05
        + repetition_score * 0.10
        + punctuation_score * 0.10
        + noisy_symbol_score * 0.14
        + symbol_cluster_score * 0.07
        + word_length_score * 0.10
    )
    noise_penalty = min(
        (noisy_symbol_ratio * 0.55) + (symbol_cluster_ratio * 0.35) + (replacement_ratio * 0.8),
        0.35,
    )
    final_score = round(_clamp(weighted - noise_penalty), 4)

    return final_score, {
        "printable_ratio": round(printable_ratio, 4),
        "control_ratio": round(control_ratio, 4),
        "alpha_token_ratio": round(alpha_token_ratio, 4),
        "digit_token_ratio": round(digit_token_ratio, 4),
        "replacement_ratio": round(replacement_ratio, 4),
        "repetition_ratio": round(repetition_ratio, 4),
        "punctuation_ratio": round(punctuation_ratio, 4),
        "noisy_symbol_ratio": round(noisy_symbol_ratio, 4),
        "symbol_cluster_ratio": round(symbol_cluster_ratio, 4),
        "noise_penalty": round(noise_penalty, 4),
        "average_word_length": round(average_word_length, 4),
        "subscores": {
            "printable": round(printable_score, 4),
            "control": round(control_score, 4),
            "replacement": round(replacement_score, 4),
            "alpha_tokens": round(alpha_score, 4),
            "digit_tokens": round(digit_score, 4),
            "repetition": round(repetition_score, 4),
            "punctuation": round(punctuation_score, 4),
            "noisy_symbols": round(noisy_symbol_score, 4),
            "symbol_clusters": round(symbol_cluster_score, 4),
            "word_length": round(word_length_score, 4),
        },
    }


def score_relevance(text: str, *, config: QualityConfig = DEFAULT_QUALITY_CONFIG) -> tuple[float, dict]:
    lowered = text.lower()
    tokens = _tokenize(lowered)
    total_tokens = max(len(tokens), 1)

    positive_hits = sum(1 for token in tokens if token in config.positive_keywords)
    ontology_hits = sum(1 for token in tokens if token in _ONTOLOGY_LEXICON)
    negative_hits = sum(1 for token in tokens if token in config.noise_keywords)
    positive_density = positive_hits / total_tokens
    ontology_density = ontology_hits / total_tokens
    negative_density = negative_hits / total_tokens

    phrase_hits = sum(1 for phrase in config.noise_phrases if phrase in lowered)
    negative_phrase_penalty = min(phrase_hits * 0.12, 0.36)

    category_hits = {
        "ritual_keywords": sum(1 for token in tokens if token in _RITUAL_KEYWORDS),
        "ontology_terms": ontology_hits,
        "tradition_tags": sum(
            1
            for tradition_tag in TRADITION_VOCABULARY
            if tradition_tag in lowered or tradition_tag.replace("_", " ") in lowered
        ),
    }
    categories_present = sum(1 for value in category_hits.values() if value > 0)
    coherence_score = _clamp(categories_present / 3.0)

    weighted = (
        0.22
        + positive_density * 5.0
        + ontology_density * 3.0
        + coherence_score * 0.18
        - negative_density * 4.4
        - negative_phrase_penalty
    )
    final_score = round(_clamp(weighted), 4)

    return final_score, {
        "positive_hits": positive_hits,
        "ontology_hits": ontology_hits,
        "negative_hits": negative_hits,
        "positive_density": round(positive_density, 4),
        "ontology_density": round(ontology_density, 4),
        "negative_density": round(negative_density, 4),
        "negative_phrase_hits": phrase_hits,
        "coherence_score": round(coherence_score, 4),
    }


def classify_relevance_state(relevance_score: float, *, config: QualityConfig = DEFAULT_QUALITY_CONFIG) -> RelevanceState:
    if relevance_score < config.relevance_filter_threshold:
        return RelevanceState.filtered
    if relevance_score < config.relevance_accept_threshold:
        return RelevanceState.borderline
    return RelevanceState.accepted


def evaluate_passage_quality(text: str, *, config: QualityConfig = DEFAULT_QUALITY_CONFIG) -> PassageQualityAssessment:
    usability_score, usability_notes = score_usability(text)
    relevance_score, relevance_notes = score_relevance(text, config=config)
    relevance_state = classify_relevance_state(relevance_score, config=config)
    return PassageQualityAssessment(
        usability_score=usability_score,
        relevance_score=relevance_score,
        relevance_state=relevance_state,
        notes={
            "usability": usability_notes,
            "relevance": relevance_notes,
        },
        quality_version=config.quality_version,
    )
