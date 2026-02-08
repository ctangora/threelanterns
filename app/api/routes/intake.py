from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import DiscoverRequest, DiscoverResponse, RegisterRequest, RegisterResponse
from app.services.intake import discover_local_sources, register_source

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
    text, source = register_source(
        db,
        request,
        actor=settings.operator_id,
        correlation_id=f"intake-register:{request.source_path}",
    )
    db.commit()
    return RegisterResponse(text_id=text.text_id, source_id=source.source_id)

