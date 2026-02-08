import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.enums import ReprocessTriggerMode
from app.models.core import IngestionJob
from app.schemas import RegisterRequest
from app.services.intake import discover_local_sources, register_source
from app.services.records import get_audit_events, get_record, infer_object_type
from app.services.review import apply_bulk_review, apply_review_decision, review_metrics, review_queue
from app.services.search import search_records
from app.services.validation import ValidationError
from app.services.workflows.ingestion import create_ingestion_job
from app.services.workflows.reprocess import enqueue_reprocess_job, list_reprocess_jobs

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


def _read_float_query(request: Request, key: str) -> float | None:
    raw = request.query_params.get(key)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not (0.0 <= value <= 1.0):
        return None
    return value


def _read_optional_bool_query(request: Request, key: str) -> bool | None:
    raw = request.query_params.get(key)
    if raw is None or raw.strip() == "":
        return None
    lowered = raw.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _query_string(values: dict[str, str | int | float | bool | None]) -> str:
    filtered = {key: value for key, value in values.items() if value is not None and str(value) != ""}
    return urlencode(filtered)


def _render_review_page(request: Request, db: Session, *, kind: str, title: str):
    page = _read_positive_int_query(request, "page", 1)
    page_size = _read_positive_int_query(request, "page_size", 50)
    state = request.query_params.get("state", "proposed")
    source_id = request.query_params.get("source_id")
    min_confidence = _read_float_query(request, "min_confidence")
    needs_reprocess = _read_optional_bool_query(request, "needs_reprocess") if kind == "passage" else None
    max_untranslated_ratio = _read_float_query(request, "max_untranslated_ratio") if kind == "passage" else None
    detected_language = request.query_params.get("detected_language") if kind == "passage" else None
    sort_by = request.query_params.get("sort_by", "created_at")
    sort_dir = request.query_params.get("sort_dir", "asc")
    error: str | None = None
    try:
        queue = review_queue(
            db,
            kind,
            page=page,
            page_size=page_size,
            max_page_size=200,
            state=state,
            source_id=source_id,
            min_confidence=min_confidence,
            needs_reprocess=needs_reprocess,
            max_untranslated_ratio=max_untranslated_ratio,
            detected_language=detected_language,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except ValidationError as exc:
        queue = {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "state": state,
            "source_id": source_id,
            "min_confidence": min_confidence,
            "needs_reprocess": needs_reprocess,
            "max_untranslated_ratio": max_untranslated_ratio,
            "detected_language": detected_language,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }
        error = str(exc)

    rendered_items: list[dict] = []
    for item in queue["items"]:
        payload_pretty = json.dumps(item, indent=2, ensure_ascii=True)
        rendered_items.append({**item, "payload_pretty": payload_pretty})

    has_prev = queue["page"] > 1
    has_next = queue["page"] * queue["page_size"] < queue["total"]
    prev_query = _query_string(
        {
            "page": max(1, queue["page"] - 1),
            "page_size": queue["page_size"],
            "state": queue["state"],
            "source_id": queue["source_id"],
            "min_confidence": queue["min_confidence"],
            "needs_reprocess": queue["needs_reprocess"],
            "max_untranslated_ratio": queue["max_untranslated_ratio"],
            "detected_language": queue["detected_language"],
            "sort_by": queue["sort_by"],
            "sort_dir": queue["sort_dir"],
        }
    )
    next_query = _query_string(
        {
            "page": queue["page"] + 1,
            "page_size": queue["page_size"],
            "state": queue["state"],
            "source_id": queue["source_id"],
            "min_confidence": queue["min_confidence"],
            "needs_reprocess": queue["needs_reprocess"],
            "max_untranslated_ratio": queue["max_untranslated_ratio"],
            "detected_language": queue["detected_language"],
            "sort_by": queue["sort_by"],
            "sort_dir": queue["sort_dir"],
        }
    )
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
            "prev_query": prev_query,
            "next_query": next_query,
            "state": queue["state"],
            "source_id": queue["source_id"],
            "min_confidence": queue["min_confidence"],
            "needs_reprocess": queue["needs_reprocess"],
            "max_untranslated_ratio": queue["max_untranslated_ratio"],
            "detected_language": queue["detected_language"],
            "sort_by": queue["sort_by"],
            "sort_dir": queue["sort_dir"],
            "error": error,
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


@router.get("/review/metrics")
def review_metrics_page(request: Request, db: Session = Depends(get_db)):
    metrics = review_metrics(db)
    return templates.TemplateResponse(request, "review_metrics.html", {"metrics": metrics})


@router.get("/review/reprocess-jobs")
def review_reprocess_jobs_page(request: Request, db: Session = Depends(get_db)):
    page = _read_positive_int_query(request, "page", 1)
    page_size = _read_positive_int_query(request, "page_size", 50)
    status = request.query_params.get("status")
    trigger_mode = request.query_params.get("trigger_mode")
    passage_id = request.query_params.get("passage_id")
    error: str | None = None

    try:
        payload = list_reprocess_jobs(
            db,
            status=status,
            trigger_mode=trigger_mode,
            passage_id=passage_id,
            page=page,
            page_size=page_size,
            max_page_size=200,
        )
    except ValidationError as exc:
        payload = {"items": [], "total": 0, "page": page, "page_size": page_size}
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "review_reprocess_jobs.html",
        {
            "items": payload["items"],
            "total": payload["total"],
            "page": payload["page"],
            "page_size": payload["page_size"],
            "status": status or "",
            "trigger_mode": trigger_mode or "",
            "passage_id": passage_id or "",
            "has_prev": payload["page"] > 1,
            "has_next": payload["page"] * payload["page_size"] < payload["total"],
            "prev_query": _query_string(
                {
                    "page": max(1, payload["page"] - 1),
                    "page_size": payload["page_size"],
                    "status": status,
                    "trigger_mode": trigger_mode,
                    "passage_id": passage_id,
                }
            ),
            "next_query": _query_string(
                {
                    "page": payload["page"] + 1,
                    "page_size": payload["page_size"],
                    "status": status,
                    "trigger_mode": trigger_mode,
                    "passage_id": passage_id,
                }
            ),
            "error": error,
        },
    )


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


@router.post("/review/{kind}/bulk")
def review_bulk_submit(
    request: Request,
    kind: str,
    object_ids: list[str] = Form(default_factory=list),
    decision: str = Form(...),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.enums import ReviewDecisionEnum

    try:
        apply_bulk_review(
            db,
            object_type=kind,
            object_ids=object_ids,
            decision=ReviewDecisionEnum(decision),
            notes=notes,
            actor=settings.operator_id,
            correlation_id=f"web-review-bulk:{kind}",
        )
        db.commit()
    except (ValidationError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    referer = request.headers.get("referer") or f"/review/{kind}s"
    return RedirectResponse(url=referer, status_code=303)


@router.post("/review/passages/{object_id}/reprocess")
def reprocess_passage_submit(
    request: Request,
    object_id: str,
    reason: str = Form("Manual review requested reprocess"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        enqueue_reprocess_job(
            db,
            passage_id=object_id,
            actor=settings.operator_id,
            trigger_mode=ReprocessTriggerMode.manual,
            reason=reason,
            correlation_id=f"web-reprocess:{object_id}",
        )
        db.commit()
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    referer = request.headers.get("referer") or "/review/passages"
    return RedirectResponse(url=referer, status_code=303)


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


@router.get("/search")
def search_page(request: Request, db: Session = Depends(get_db)):
    query = request.query_params.get("q", "")
    object_type = request.query_params.get("object_type") or None
    tag = request.query_params.get("tag") or None
    culture_region = request.query_params.get("culture_region") or None
    review_state = request.query_params.get("review_state") or None
    limit = _read_positive_int_query(request, "limit", 100)

    hits: list[dict] = []
    error: str | None = None
    if any([query.strip(), object_type, tag, culture_region, review_state]):
        try:
            hits = search_records(
                db,
                query=query,
                object_type=object_type,
                tag=tag,
                culture_region=culture_region,
                review_state=review_state,
                limit=limit,
            )
        except ValidationError as exc:
            error = str(exc)

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "hits": hits,
            "error": error,
            "q": query,
            "object_type": object_type or "",
            "tag": tag or "",
            "culture_region": culture_region or "",
            "review_state": review_state or "",
            "limit": limit,
        },
    )
