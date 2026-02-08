from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import (
    TuningApplyRequest,
    TuningApplyResponse,
    TuningPreviewRequest,
    TuningPreviewResponse,
    TuningProfileRequest,
    TuningProfileResponse,
    TuningProfilesResponse,
    TuningRunResponse,
    TuningRunsResponse,
)
from app.services.validation import ValidationError
from app.services.workflows.tuning import (
    create_tuning_apply_run,
    create_tuning_preview_run,
    get_default_profile,
    get_profile,
    get_tuning_run,
    list_profiles,
    list_tuning_runs,
    promote_profile_as_default,
    upsert_profile,
)

router = APIRouter(prefix="/api/v1/tuning", tags=["tuning"])


@router.get("/profiles", response_model=TuningProfilesResponse)
def profiles(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> TuningProfilesResponse:
    default_profile = get_default_profile(db, actor=settings.operator_id)
    items = list_profiles(db)
    return TuningProfilesResponse(
        default_profile_id=default_profile.profile_id,
        items=[TuningProfileResponse.from_orm(item) for item in items],
    )


@router.post("/profiles", response_model=TuningProfileResponse)
def create_profile(
    request: TuningProfileRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TuningProfileResponse:
    profile = upsert_profile(
        db,
        profile_id=None,
        name=request.name,
        thresholds_json=request.thresholds_json,
        lexicons_json=request.lexicons_json,
        segmentation_json=request.segmentation_json,
        actor=settings.operator_id,
    )
    db.commit()
    return TuningProfileResponse.from_orm(profile)


@router.put("/profiles/{profile_id}", response_model=TuningProfileResponse)
def update_profile(
    profile_id: str,
    request: TuningProfileRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TuningProfileResponse:
    profile = upsert_profile(
        db,
        profile_id=profile_id,
        name=request.name,
        thresholds_json=request.thresholds_json,
        lexicons_json=request.lexicons_json,
        segmentation_json=request.segmentation_json,
        actor=settings.operator_id,
    )
    db.commit()
    return TuningProfileResponse.from_orm(profile)


@router.post("/profiles/{profile_id}/promote")
def promote_profile(profile_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        promote_profile_as_default(db, profile_id=profile_id, actor=settings.operator_id)
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"status": "ok", "default_profile_id": profile_id}


@router.post("/runs/preview", response_model=TuningPreviewResponse)
def preview_run(
    request: TuningPreviewRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TuningPreviewResponse:
    try:
        result = create_tuning_preview_run(
            db,
            source_id=request.source_id,
            profile_id=request.profile_id,
            parser_strategy=request.parser_strategy,
            actor=settings.operator_id,
        )
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return TuningPreviewResponse(run=TuningRunResponse.from_orm(result.run), summary=result.summary)


@router.post("/runs/apply", response_model=TuningApplyResponse)
def apply_run(
    request: TuningApplyRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TuningApplyResponse:
    try:
        run, job = create_tuning_apply_run(
            db,
            source_id=request.source_id,
            profile_id=request.profile_id,
            parser_strategy=request.parser_strategy,
            ai_enabled=request.ai_enabled,
            external_refs_enabled=request.external_refs_enabled,
            actor=settings.operator_id,
        )
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return TuningApplyResponse(run_id=run.run_id, job_id=job.job_id, status="created")


@router.get("/runs/{run_id}", response_model=TuningRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)) -> TuningRunResponse:
    try:
        run = get_tuning_run(db, run_id=run_id)
    except ValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TuningRunResponse.from_orm(run)


@router.get("/runs", response_model=TuningRunsResponse)
def runs(source_id: str | None = None, db: Session = Depends(get_db)) -> TuningRunsResponse:
    items = list_tuning_runs(db, source_id=source_id, limit=100)
    return TuningRunsResponse(items=[TuningRunResponse.from_orm(item) for item in items])

