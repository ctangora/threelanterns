import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.core import IngestionJob
from app.schemas import RegisterRequest
from app.services.intake import discover_local_sources, register_source
from app.services.records import get_audit_events, get_record, infer_object_type
from app.services.review import apply_review_decision, review_queue
from app.services.validation import ValidationError
from app.services.workflows.ingestion import create_ingestion_job

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["web"])


def _read_positive_int_query(request: Request, key: str, default: int) -> int:
    raw = request.query_params.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 1 else default


def _render_review_page(request: Request, db: Session, *, kind: str, title: str):
    page = _read_positive_int_query(request, "page", 1)
    page_size = _read_positive_int_query(request, "page_size", 50)
    queue = review_queue(db, kind, page=page, page_size=page_size, max_page_size=200)

    rendered_items: list[dict] = []
    for item in queue["items"]:
        payload_pretty = json.dumps(item, indent=2, ensure_ascii=True)
        rendered_items.append({**item, "payload_pretty": payload_pretty})

    has_prev = queue["page"] > 1
    has_next = queue["page"] * queue["page_size"] < queue["total"]
    return templates.TemplateResponse(
        request,
        "review_list.html",
        {
            "title": title,
            "kind": kind,
            "items": rendered_items,
            "total": queue["total"],
            "page": queue["page"],
            "page_size": queue["page_size"],
            "has_prev": has_prev,
            "has_next": has_next,
            "prev_page": max(1, queue["page"] - 1),
            "next_page": queue["page"] + 1,
            "base_path": f"/review/{kind}s",
        },
    )


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/intake", status_code=303)


@router.get("/intake")
def intake_page(request: Request, settings: Settings = Depends(get_settings)):
    files = discover_local_sources(max_files=25, root_path=str(settings.ingest_root))
    return templates.TemplateResponse(
        request,
        "intake.html",
        {"files": files, "ingest_root": str(settings.ingest_root)},
    )


@router.post("/intake/register")
def intake_register(
    request: Request,
    source_path: str = Form(...),
    rights_status: str = Form("public_domain"),
    rights_evidence: str = Form("Local research corpus"),
    provenance_summary: str = Form("Initial Milestone 2 source registration"),
    holding_institution: str = Form("Local Reference Library"),
    accession_or_citation: str = Form("internal-local"),
    source_provenance_note: str = Form("Imported from local __Reference__ corpus"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    register_req = RegisterRequest(
        source_path=source_path,
        rights_status=rights_status,
        rights_evidence=rights_evidence,
        provenance_summary=provenance_summary,
        holding_institution=holding_institution,
        accession_or_citation=accession_or_citation,
        source_provenance_note=source_provenance_note,
    )
    try:
        _, source = register_source(
            db,
            register_req,
            actor=settings.operator_id,
            correlation_id=f"web-intake:{source_path}",
        )
        create_ingestion_job(
            db,
            source_id=source.source_id,
            actor=settings.operator_id,
            idempotency_key=f"web-intake:{source.source_id}",
            correlation_id=f"web-job:{source.source_id}",
        )
        db.commit()
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/jobs", status_code=303)


@router.get("/jobs")
def jobs_page(request: Request, db: Session = Depends(get_db)):
    jobs = list(db.scalars(select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(200)))
    return templates.TemplateResponse(request, "jobs.html", {"jobs": jobs})


@router.get("/review/passages")
def review_passages(request: Request, db: Session = Depends(get_db)):
    return _render_review_page(request, db, kind="passage", title="Passage Review Queue")


@router.get("/review/tags")
def review_tags(request: Request, db: Session = Depends(get_db)):
    return _render_review_page(request, db, kind="tag", title="Tag Review Queue")


@router.get("/review/links")
def review_links(request: Request, db: Session = Depends(get_db)):
    return _render_review_page(request, db, kind="link", title="Commonality Link Review Queue")


@router.get("/review/flags")
def review_flags(request: Request, db: Session = Depends(get_db)):
    return _render_review_page(request, db, kind="flag", title="Flag Review Queue")


@router.post("/review/{kind}/{object_id}")
def review_submit(
    kind: str,
    object_id: str,
    decision: str = Form(...),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.enums import ReviewDecisionEnum

    try:
        apply_review_decision(
            db,
            object_type=kind,
            object_id=object_id,
            decision=ReviewDecisionEnum(decision),
            notes=notes,
            actor=settings.operator_id,
            correlation_id=f"web-review:{kind}:{object_id}",
        )
        db.commit()
    except (ValidationError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/review/{kind}s", status_code=303)


@router.get("/records/{object_id}")
def record_page(request: Request, object_id: str, db: Session = Depends(get_db)):
    object_type = infer_object_type(object_id)
    payload = get_record(db, object_type, object_id)
    return templates.TemplateResponse(
        request,
        "record.html",
        {"object_id": object_id, "object_type": object_type, "payload_json": json.dumps(payload, indent=2, default=str)},
    )


@router.get("/audit/{object_id}")
def audit_page(request: Request, object_id: str, db: Session = Depends(get_db)):
    object_type = infer_object_type(object_id)
    events = get_audit_events(db, object_type, object_id)
    return templates.TemplateResponse(
        request,
        "audit.html",
        {"object_id": object_id, "object_type": object_type, "events_json": json.dumps(events, indent=2, default=str)},
    )
