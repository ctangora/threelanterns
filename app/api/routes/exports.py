import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import PublishState, ReviewerState
from app.models.core import CommonalityLink, FlagRecord, PassageEvidence, PassageReprocessJob, RitualPatternTag

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


def _csv_response(*, filename: str, rows: list[dict[str, str]]) -> Response:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write("")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    content_disposition = f'attachment; filename="{timestamp}_{filename}"'
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/passages.csv")
def export_passages(
    state: str = Query(default=PublishState.eligible.value, pattern="^(blocked|eligible|published)$"),
    db: Session = Depends(get_db),
) -> Response:
    rows = db.scalars(select(PassageEvidence).where(PassageEvidence.publish_state == PublishState(state))).all()
    payload: list[dict[str, str]] = []
    for row in rows:
        latest_reason_code = db.scalar(
            select(PassageReprocessJob.trigger_reason_code)
            .where(PassageReprocessJob.passage_id == row.passage_id)
            .order_by(PassageReprocessJob.created_at.desc())
            .limit(1)
        )
        payload.append(
            {
                "passage_id": row.passage_id,
                "text_id": row.text_id,
                "source_id": row.source_id,
                "source_span_locator": row.source_span_locator,
                "original_language": row.original_language,
                "normalized_language": row.normalized_language,
                "detected_language_code": row.detected_language_code or "",
                "detected_language_label": row.detected_language_label or "",
                "untranslated_ratio": str(row.untranslated_ratio),
                "translation_status": row.translation_status.value
                if hasattr(row.translation_status, "value")
                else str(row.translation_status),
                "needs_reprocess": str(bool(row.needs_reprocess)).lower(),
                "usability_score": str(row.usability_score),
                "relevance_score": str(row.relevance_score),
                "relevance_state": row.relevance_state.value
                if hasattr(row.relevance_state, "value")
                else str(row.relevance_state),
                "trigger_reason_code_last": latest_reason_code or "",
                "extraction_confidence": str(row.extraction_confidence),
                "reviewer_state": row.reviewer_state.value,
                "publish_state": row.publish_state.value,
                "excerpt_normalized": row.excerpt_normalized,
            }
        )
    return _csv_response(filename="passages.csv", rows=payload)


@router.get("/tags.csv")
def export_tags(
    state: str = Query(default=ReviewerState.approved.value, pattern="^(proposed|approved|rejected|needs_revision)$"),
    db: Session = Depends(get_db),
) -> Response:
    rows = db.scalars(select(RitualPatternTag).where(RitualPatternTag.reviewer_state == ReviewerState(state))).all()
    payload: list[dict[str, str]] = []
    for row in rows:
        payload.append(
            {
                "tag_id": row.tag_id,
                "ontology_dimension": row.ontology_dimension,
                "controlled_term": row.controlled_term,
                "confidence": str(row.confidence),
                "evidence_ids": ",".join(row.evidence_ids),
                "reviewer_state": row.reviewer_state.value,
                "rationale_note": row.rationale_note or "",
            }
        )
    return _csv_response(filename="tags.csv", rows=payload)


@router.get("/links.csv")
def export_links(
    state: str = Query(default=ReviewerState.approved.value, pattern="^(proposed|approved|rejected|needs_revision)$"),
    db: Session = Depends(get_db),
) -> Response:
    rows = db.scalars(select(CommonalityLink).where(CommonalityLink.reviewer_decision == ReviewerState(state))).all()
    payload: list[dict[str, str]] = []
    for row in rows:
        payload.append(
            {
                "link_id": row.link_id,
                "source_entity_id": row.source_entity_id,
                "target_entity_id": row.target_entity_id,
                "relation_type": row.relation_type.value if hasattr(row.relation_type, "value") else str(row.relation_type),
                "weighted_similarity_score": str(row.weighted_similarity_score),
                "evidence_ids": ",".join(row.evidence_ids),
                "reviewer_decision": row.reviewer_decision.value,
                "decision_note": row.decision_note or "",
            }
        )
    return _csv_response(filename="links.csv", rows=payload)


@router.get("/flags.csv")
def export_flags(
    state: str = Query(default=ReviewerState.approved.value, pattern="^(proposed|approved|rejected|needs_revision)$"),
    db: Session = Depends(get_db),
) -> Response:
    rows = db.scalars(select(FlagRecord).where(FlagRecord.reviewer_state == ReviewerState(state))).all()
    payload: list[dict[str, str]] = []
    for row in rows:
        payload.append(
            {
                "flag_id": row.flag_id,
                "object_type": row.object_type.value if hasattr(row.object_type, "value") else str(row.object_type),
                "object_id": row.object_id,
                "flag_type": row.flag_type,
                "severity": row.severity,
                "rationale": row.rationale,
                "evidence_ids": ",".join(row.evidence_ids),
                "reviewer_state": row.reviewer_state.value,
            }
        )
    return _csv_response(filename="flags.csv", rows=payload)
