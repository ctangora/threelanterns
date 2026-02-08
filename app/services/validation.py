from app.constants import COMMONALITY_RELATION_TYPES, FLAG_TYPES, ONTOLOGY_DIMENSIONS, REGION_VOCABULARY, TRADITION_VOCABULARY
from app.enums import ReviewDecisionEnum


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_region(region: str) -> None:
    require(region in REGION_VOCABULARY, f"Invalid region vocabulary value: {region}")


def validate_traditions(traditions: list[str]) -> None:
    require(bool(traditions), "At least one tradition tag is required")
    for value in traditions:
        require(value in TRADITION_VOCABULARY, f"Invalid tradition vocabulary value: {value}")


def validate_confidence(score: float, field_name: str) -> None:
    require(0.0 <= score <= 1.0, f"{field_name} must be between 0.0 and 1.0")


def validate_ontology_term(dimension: str, term: str) -> bool:
    if dimension not in ONTOLOGY_DIMENSIONS:
        return False
    return term in ONTOLOGY_DIMENSIONS[dimension]


def validate_relation_type(value: str) -> None:
    require(value in COMMONALITY_RELATION_TYPES, f"Invalid relation type: {value}")


def validate_flag_type(value: str) -> None:
    require(value in FLAG_TYPES, f"Invalid flag type: {value}")


def validate_review_input(decision: ReviewDecisionEnum, notes: str | None) -> None:
    if decision in {ReviewDecisionEnum.reject, ReviewDecisionEnum.needs_revision}:
        require(bool(notes and notes.strip()), "Notes are required for reject/needs_revision")

