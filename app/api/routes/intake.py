from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import (
    BatchRegisterRequest,
    BatchRegisterResponse,
    BatchRegisterResult,
    DiscoverRequest,
    DiscoverResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.services.intake import discover_local_sources, register_source_with_outcome
from app.services.validation import ValidationError

router = APIRouter(prefix="/api/v1/intake", tags=["intake"])


@router.post("/discover", response_model=DiscoverResponse)
def discover_sources(
    request: DiscoverRequest,
    settings: Settings = Depends(get_settings),
) -> DiscoverResponse:
    files = discover_local_sources(max_files=request.max_files, root_path=request.root_path or str(settings.ingest_root))
    return DiscoverResponse(count=len(files), files=files)


@router.post("/register", response_model=RegisterResponse)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RegisterResponse:
    try:
        outcome = register_source_with_outcome(
            db,
            request,
            actor=settings.operator_id,
            correlation_id=f"intake-register:{request.source_path}",
        )
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return RegisterResponse(
        text_id=outcome.text.text_id,
        source_id=outcome.source.source_id,
        registration_status=outcome.registration_status,
        duplicate_of_source_id=outcome.duplicate_of_source_id,
        witness_group_id=outcome.witness_group_id,
    )


@router.post("/register/batch", response_model=BatchRegisterResponse)
def register_batch(
    request: BatchRegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BatchRegisterResponse:
    results: list[BatchRegisterResult] = []
    created = 0
    exact_duplicates = 0
    alternate_witnesses = 0
    failed = 0

    for item in request.items:
        try:
            outcome = register_source_with_outcome(
                db,
                item,
                actor=settings.operator_id,
                correlation_id=f"intake-register-batch:{item.source_path}",
            )
        except Exception as exc:
            db.rollback()
            failed += 1
            results.append(
                BatchRegisterResult(
                    source_path=item.source_path,
                    status="failed",
                    error=f"{exc.__class__.__name__}: {exc}",
                )
            )
            if not request.continue_on_error:
                break
            continue
        db.commit()

        if outcome.registration_status == "created":
            created += 1
        elif outcome.registration_status == "exact_duplicate":
            exact_duplicates += 1
        elif outcome.registration_status == "alternate_witness":
            alternate_witnesses += 1

        results.append(
            BatchRegisterResult(
                source_path=item.source_path,
                status=outcome.registration_status,
                text_id=outcome.text.text_id,
                source_id=outcome.source.source_id,
                duplicate_of_source_id=outcome.duplicate_of_source_id,
                witness_group_id=outcome.witness_group_id,
            )
        )

    return BatchRegisterResponse(
        total=len(request.items),
        created=created,
        exact_duplicates=exact_duplicates,
        alternate_witnesses=alternate_witnesses,
        failed=failed,
        results=results,
    )
