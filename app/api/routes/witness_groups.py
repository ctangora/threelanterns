from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.core import ConsolidatedPassage, WitnessGroup, WitnessGroupMember
from app.services.validation import ValidationError
from app.services.witness import consolidate_group

router = APIRouter(prefix="/api/v1/witness-groups", tags=["witness-groups"])


@router.get("")
def list_groups(
    status: str | None = Query(default=None, pattern="^(active|needs_review|archived)$"),
    db: Session = Depends(get_db),
):
    stmt = select(WitnessGroup)
    if status:
        stmt = stmt.where(WitnessGroup.group_status == status)
    stmt = stmt.order_by(WitnessGroup.created_at.desc()).limit(200)
    rows = list(db.scalars(stmt))
    items = []
    for row in rows:
        member_count = db.scalar(
            select(func.count()).select_from(WitnessGroupMember).where(WitnessGroupMember.group_id == row.group_id)
        )
        items.append(
            {
                "group_id": row.group_id,
                "canonical_text_id": row.canonical_text_id,
                "group_status": row.group_status,
                "match_method": row.match_method,
                "match_score": row.match_score,
                "member_count": int(member_count or 0),
            }
        )
    return {"items": items}


@router.get("/{group_id}")
def get_group(group_id: str, db: Session = Depends(get_db)):
    group = db.get(WitnessGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group_not_found")
    members = list(db.scalars(select(WitnessGroupMember).where(WitnessGroupMember.group_id == group_id)))
    consolidated_count = db.scalar(
        select(func.count()).select_from(ConsolidatedPassage).where(ConsolidatedPassage.group_id == group_id)
    )
    return {
        "group_id": group.group_id,
        "canonical_text_id": group.canonical_text_id,
        "group_status": group.group_status,
        "match_method": group.match_method,
        "match_score": group.match_score,
        "members": [
            {
                "source_id": member.source_id,
                "member_role": member.member_role,
                "parser_strategy": member.parser_strategy,
                "membership_reason": member.membership_reason,
            }
            for member in members
        ],
        "consolidated_count": int(consolidated_count or 0),
    }


@router.post("/recompute/{group_id}")
def recompute_group(
    group_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = consolidate_group(db, group_id=group_id, actor=settings.operator_id)
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"status": "ok", **result}
