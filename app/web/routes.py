import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import REPROCESS_REASON_LABELS
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
from app.services.witness import consolidate_group
from app.services.workflows.tuning import (
    create_tuning_apply_run,
    create_tuning_preview_run,
    get_default_profile,
    get_profile,
    list_profiles,
    list_tuning_runs,
    promote_profile_as_default,
    upsert_profile,
)

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


def _read_auto_refresh_seconds(request: Request, key: str, default: int = 0) -> int:
    raw = request.query_params.get(key)
    if raw is None or raw.strip() == "":
        return default
    if raw.strip() == "off":
        return 0
    try:
        value = int(raw)
    except ValueError:
        return default
    if value in {0, 10, 30, 60}:
        return value
    return default


def _query_string(values: dict[str, str | int | float | bool | None]) -> str:
    filtered = {key: value for key, value in values.items() if value is not None and str(value) != ""}
    return urlencode(filtered)


def _render_review_page(request: Request, db: Session, *, kind: str, title: str):
    page = _read_positive_int_query(request, "page", 1)
    page_size = _read_positive_int_query(request, "page_size", 50)
    state = request.query_params.get("state", "proposed")
    source_id = request.query_params.get("source_id")
    min_confidence = _read_float_query(request, "min_confidence")
    max_confidence = _read_float_query(request, "max_confidence")
    needs_reprocess = _read_optional_bool_query(request, "needs_reprocess") if kind == "passage" else None
    min_untranslated_ratio = _read_float_query(request, "min_untranslated_ratio") if kind == "passage" else None
    max_untranslated_ratio = _read_float_query(request, "max_untranslated_ratio") if kind == "passage" else None
    detected_language = request.query_params.get("detected_language") if kind == "passage" else None
    min_usability = _read_float_query(request, "min_usability") if kind == "passage" else None
    max_usability = _read_float_query(request, "max_usability") if kind == "passage" else None
    min_relevance = _read_float_query(request, "min_relevance") if kind == "passage" else None
    max_relevance = _read_float_query(request, "max_relevance") if kind == "passage" else None
    relevance_state = request.query_params.get("relevance_state") if kind == "passage" else None
    include_filtered = _read_optional_bool_query(request, "include_filtered") if kind == "passage" else None
    if include_filtered is None and kind == "passage":
        include_filtered = False
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
            max_confidence=max_confidence,
            needs_reprocess=needs_reprocess,
            min_untranslated_ratio=min_untranslated_ratio,
            max_untranslated_ratio=max_untranslated_ratio,
            detected_language=detected_language,
            min_usability=min_usability,
            max_usability=max_usability,
            min_relevance=min_relevance,
            max_relevance=max_relevance,
            relevance_state=relevance_state,
            include_filtered=bool(include_filtered) if kind == "passage" else False,
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
            "max_confidence": max_confidence,
            "needs_reprocess": needs_reprocess,
            "min_untranslated_ratio": min_untranslated_ratio,
            "max_untranslated_ratio": max_untranslated_ratio,
            "detected_language": detected_language,
            "min_usability": min_usability,
            "max_usability": max_usability,
            "min_relevance": min_relevance,
            "max_relevance": max_relevance,
            "relevance_state": relevance_state,
            "include_filtered": include_filtered,
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
            "max_confidence": queue["max_confidence"],
            "needs_reprocess": queue["needs_reprocess"],
            "min_untranslated_ratio": queue["min_untranslated_ratio"],
            "max_untranslated_ratio": queue["max_untranslated_ratio"],
            "detected_language": queue["detected_language"],
            "min_usability": queue["min_usability"],
            "max_usability": queue["max_usability"],
            "min_relevance": queue["min_relevance"],
            "max_relevance": queue["max_relevance"],
            "relevance_state": queue["relevance_state"],
            "include_filtered": queue["include_filtered"],
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
            "max_confidence": queue["max_confidence"],
            "needs_reprocess": queue["needs_reprocess"],
            "min_untranslated_ratio": queue["min_untranslated_ratio"],
            "max_untranslated_ratio": queue["max_untranslated_ratio"],
            "detected_language": queue["detected_language"],
            "min_usability": queue["min_usability"],
            "max_usability": queue["max_usability"],
            "min_relevance": queue["min_relevance"],
            "max_relevance": queue["max_relevance"],
            "relevance_state": queue["relevance_state"],
            "include_filtered": queue["include_filtered"],
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
            "max_confidence": queue["max_confidence"],
            "needs_reprocess": queue["needs_reprocess"],
            "min_untranslated_ratio": queue["min_untranslated_ratio"],
            "max_untranslated_ratio": queue["max_untranslated_ratio"],
            "detected_language": queue["detected_language"],
            "min_usability": queue["min_usability"],
            "max_usability": queue["max_usability"],
            "min_relevance": queue["min_relevance"],
            "max_relevance": queue["max_relevance"],
            "relevance_state": queue["relevance_state"],
            "include_filtered": queue["include_filtered"],
            "sort_by": queue["sort_by"],
            "sort_dir": queue["sort_dir"],
            "reprocess_reason_options": sorted(REPROCESS_REASON_LABELS.items()),
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
    reason_code = request.query_params.get("reason_code")
    passage_id = request.query_params.get("passage_id")
    auto_refresh_seconds = _read_auto_refresh_seconds(request, "auto_refresh", default=0)
    error: str | None = None

    try:
        payload = list_reprocess_jobs(
            db,
            status=status,
            trigger_mode=trigger_mode,
            reason_code=reason_code,
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
            "reason_code": reason_code or "",
            "passage_id": passage_id or "",
            "auto_refresh": auto_refresh_seconds,
            "auto_refresh_enabled": auto_refresh_seconds > 0,
            "has_prev": payload["page"] > 1,
            "has_next": payload["page"] * payload["page_size"] < payload["total"],
            "prev_query": _query_string(
                {
                    "page": max(1, payload["page"] - 1),
                    "page_size": payload["page_size"],
                    "status": status,
                    "trigger_mode": trigger_mode,
                    "reason_code": reason_code,
                    "passage_id": passage_id,
                    "auto_refresh": auto_refresh_seconds if auto_refresh_seconds > 0 else "off",
                }
            ),
            "next_query": _query_string(
                {
                    "page": payload["page"] + 1,
                    "page_size": payload["page_size"],
                    "status": status,
                    "trigger_mode": trigger_mode,
                    "reason_code": reason_code,
                    "passage_id": passage_id,
                    "auto_refresh": auto_refresh_seconds if auto_refresh_seconds > 0 else "off",
                }
            ),
            "reprocess_reason_options": sorted(REPROCESS_REASON_LABELS.items()),
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
    reason_code: str = Form("manual_operator_request"),
    reason_note: str | None = Form(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        enqueue_reprocess_job(
            db,
            passage_id=object_id,
            actor=settings.operator_id,
            trigger_mode=ReprocessTriggerMode.manual,
            reason_note=reason_note,
            reason_code=reason_code,
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


@router.get("/witness-groups")
def witness_groups_page(request: Request, db: Session = Depends(get_db)):
    status = request.query_params.get("status")
    from sqlalchemy import func
    from app.models.core import ConsolidatedPassage, WitnessGroup, WitnessGroupMember

    stmt = select(WitnessGroup)
    if status:
        stmt = stmt.where(WitnessGroup.group_status == status)
    groups = list(db.scalars(stmt.order_by(WitnessGroup.created_at.desc()).limit(200)))
    items = []
    for group in groups:
        member_count = db.scalar(
            select(func.count()).select_from(WitnessGroupMember).where(WitnessGroupMember.group_id == group.group_id)
        )
        consolidated_count = db.scalar(
            select(func.count()).select_from(ConsolidatedPassage).where(ConsolidatedPassage.group_id == group.group_id)
        )
        items.append(
            {
                "group_id": group.group_id,
                "canonical_text_id": group.canonical_text_id,
                "group_status": group.group_status,
                "match_method": group.match_method,
                "match_score": group.match_score,
                "member_count": int(member_count or 0),
                "consolidated_count": int(consolidated_count or 0),
            }
        )
    return templates.TemplateResponse(
        request,
        "witness_groups.html",
        {"items": items, "status": status or ""},
    )


@router.get("/witness-groups/{group_id}")
def witness_group_detail(request: Request, group_id: str, db: Session = Depends(get_db)):
    from app.models.core import ConsolidatedPassage, WitnessGroup, WitnessGroupMember

    group = db.get(WitnessGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group_not_found")
    members = list(db.scalars(select(WitnessGroupMember).where(WitnessGroupMember.group_id == group_id)))
    consolidated = list(
        db.scalars(select(ConsolidatedPassage).where(ConsolidatedPassage.group_id == group_id).order_by(ConsolidatedPassage.created_at.desc()).limit(200))
    )
    return templates.TemplateResponse(
        request,
        "witness_group_detail.html",
        {"group": group, "members": members, "consolidated": consolidated},
    )


@router.post("/witness-groups/{group_id}/recompute")
def witness_group_recompute(group_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    try:
        consolidate_group(db, group_id=group_id, actor=settings.operator_id)
        db.commit()
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/witness-groups/{group_id}", status_code=303)


@router.get("/tuning")
def tuning_home(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    from sqlalchemy import func, or_
    from app.models.core import PassageEvidence, SourceMaterialRecord, TextRecord

    q = (request.query_params.get("q") or "").strip()
    default_profile = get_default_profile(db, actor=settings.operator_id)
    profiles = list_profiles(db)

    sources_stmt = select(SourceMaterialRecord).order_by(SourceMaterialRecord.created_at.desc()).limit(30)
    if q:
        sources_stmt = (
            select(SourceMaterialRecord)
            .join(TextRecord, TextRecord.text_id == SourceMaterialRecord.text_id)
            .where(
                or_(
                    SourceMaterialRecord.source_id == q,
                    SourceMaterialRecord.text_id == q,
                    SourceMaterialRecord.source_path.ilike(f"%{q}%"),
                    TextRecord.canonical_title.ilike(f"%{q}%"),
                )
            )
            .order_by(SourceMaterialRecord.created_at.desc())
            .limit(50)
        )
    sources = list(db.scalars(sources_stmt))

    most_recent = sources[:10]
    garbled_rows = db.execute(
        select(SourceMaterialRecord.source_id, func.avg(PassageEvidence.usability_score).label("avg_usability"))
        .join(PassageEvidence, PassageEvidence.source_id == SourceMaterialRecord.source_id)
        .group_by(SourceMaterialRecord.source_id)
        .order_by(func.avg(PassageEvidence.usability_score).asc())
        .limit(10)
    ).all()
    irrelevant_rows = db.execute(
        select(SourceMaterialRecord.source_id, func.avg(PassageEvidence.relevance_score).label("avg_relevance"))
        .join(PassageEvidence, PassageEvidence.source_id == SourceMaterialRecord.source_id)
        .group_by(SourceMaterialRecord.source_id)
        .order_by(func.avg(PassageEvidence.relevance_score).asc())
        .limit(10)
    ).all()

    return templates.TemplateResponse(
        request,
        "tuning.html",
        {
            "q": q,
            "default_profile_id": default_profile.profile_id,
            "profiles": profiles,
            "sources": sources,
            "most_recent": most_recent,
            "most_garbled": [{"source_id": source_id, "avg_usability": float(avg or 0.0)} for source_id, avg in garbled_rows],
            "most_irrelevant": [{"source_id": source_id, "avg_relevance": float(avg or 0.0)} for source_id, avg in irrelevant_rows],
        },
    )


@router.get("/tuning/source/{source_id}")
def tuning_source_page(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from sqlalchemy import func
    from app.models.core import IngestionJob, PassageEvidence, SourceMaterialRecord, TextRecord

    source = db.get(SourceMaterialRecord, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source_not_found")
    text = db.get(TextRecord, source.text_id)

    profiles = list_profiles(db)
    default_profile = get_default_profile(db, actor=settings.operator_id)
    profile_id = (request.query_params.get("profile_id") or default_profile.profile_id).strip()
    profile = get_profile(db, profile_id=profile_id)

    passages_total = int(db.scalar(select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id)) or 0)
    accepted = int(
        db.scalar(select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id, PassageEvidence.relevance_state == "accepted"))
        or 0
    )
    borderline = int(
        db.scalar(
            select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id, PassageEvidence.relevance_state == "borderline")
        )
        or 0
    )
    filtered = int(
        db.scalar(select(func.count()).select_from(PassageEvidence).where(PassageEvidence.source_id == source_id, PassageEvidence.relevance_state == "filtered"))
        or 0
    )
    avg_usability = float(
        db.scalar(select(func.avg(PassageEvidence.usability_score)).where(PassageEvidence.source_id == source_id)) or 0.0
    )
    avg_relevance = float(
        db.scalar(select(func.avg(PassageEvidence.relevance_score)).where(PassageEvidence.source_id == source_id)) or 0.0
    )
    avg_ratio = float(
        db.scalar(select(func.avg(PassageEvidence.untranslated_ratio)).where(PassageEvidence.source_id == source_id)) or 0.0
    )

    last_job = db.scalar(select(IngestionJob).where(IngestionJob.source_id == source_id).order_by(IngestionJob.created_at.desc()).limit(1))
    runs = list_tuning_runs(db, source_id=source_id, limit=20)

    return templates.TemplateResponse(
        request,
        "tuning_source.html",
        {
            "source": source,
            "text": text,
            "profiles": profiles,
            "profile": profile,
            "profile_id": profile.profile_id,
            "default_profile_id": default_profile.profile_id,
            "snapshot": {
                "passages_total": passages_total,
                "accepted": accepted,
                "borderline": borderline,
                "filtered": filtered,
                "avg_usability": round(avg_usability, 4),
                "avg_relevance": round(avg_relevance, 4),
                "avg_untranslated_ratio": round(avg_ratio, 4),
            },
            "last_job": last_job,
            "runs": runs,
            "parser_strategies": [
                ("auto_by_extension", "Auto (by extension)"),
                ("txt:clean_v1", "TXT clean v1"),
                ("txt:garble_v1", "TXT garble v1"),
                ("pdf:ocr_v0", "PDF OCR v0 (not implemented)"),
                ("images:ocr_v0", "Images OCR v0 (not implemented)"),
                ("old_english:normalize_v0", "Old English normalize v0 (not implemented)"),
            ],
        },
    )


@router.post("/tuning/profile/{profile_id}/update")
def tuning_profile_update(
    request: Request,
    profile_id: str,
    name: str = Form(...),
    relevance_accept_threshold: float = Form(0.5),
    relevance_filter_threshold: float = Form(0.3),
    usability_reprocess_threshold: float = Form(0.6),
    min_passage_length: int = Form(180),
    max_passages_per_source_override: str | None = Form(None),
    positive_keywords: str = Form(""),
    noise_keywords: str = Form(""),
    noise_phrases: str = Form(""),
    set_default: str | None = Form(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    thresholds_json = {
        "relevance_accept_threshold": relevance_accept_threshold,
        "relevance_filter_threshold": relevance_filter_threshold,
        "usability_reprocess_threshold": usability_reprocess_threshold,
    }
    lexicons_json = {
        "positive_keywords": [line.strip().lower() for line in positive_keywords.splitlines() if line.strip()],
        "noise_keywords": [line.strip().lower() for line in noise_keywords.splitlines() if line.strip()],
        "noise_phrases": [line.strip().lower() for line in noise_phrases.splitlines() if line.strip()],
    }
    override_value: int | None = None
    if max_passages_per_source_override and max_passages_per_source_override.strip():
        try:
            override_value = int(max_passages_per_source_override.strip())
        except ValueError:
            override_value = None
    segmentation_json = {
        "min_passage_length": int(min_passage_length),
        "max_passages_per_source_override": override_value,
    }
    try:
        upsert_profile(
            db,
            profile_id=profile_id,
            name=name,
            thresholds_json=thresholds_json,
            lexicons_json=lexicons_json,
            segmentation_json=segmentation_json,
            actor=settings.operator_id,
        )
        if set_default:
            promote_profile_as_default(db, profile_id=profile_id, actor=settings.operator_id)
        db.commit()
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    referer = request.headers.get("referer") or "/tuning"
    return RedirectResponse(url=referer, status_code=303)


@router.post("/tuning/source/{source_id}/preview")
def tuning_preview_submit(
    request: Request,
    source_id: str,
    profile_id: str = Form(...),
    parser_strategy: str = Form("auto_by_extension"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = create_tuning_preview_run(
            db,
            source_id=source_id,
            profile_id=profile_id,
            parser_strategy=parser_strategy,
            actor=settings.operator_id,
        )
        db.commit()
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/tuning/runs/{result.run.run_id}", status_code=303)


@router.post("/tuning/source/{source_id}/apply")
def tuning_apply_submit(
    request: Request,
    source_id: str,
    profile_id: str = Form(...),
    parser_strategy: str = Form("auto_by_extension"),
    ai_enabled: str | None = Form(None),
    external_refs_enabled: str | None = Form(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    run, job = create_tuning_apply_run(
        db,
        source_id=source_id,
        profile_id=profile_id,
        parser_strategy=parser_strategy,
        ai_enabled=bool(ai_enabled),
        external_refs_enabled=bool(external_refs_enabled),
        actor=settings.operator_id,
    )
    db.commit()
    return RedirectResponse(url=f"/jobs", status_code=303)


@router.post("/tuning/profile/{profile_id}/promote")
def tuning_promote_profile(profile_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    try:
        promote_profile_as_default(db, profile_id=profile_id, actor=settings.operator_id)
        db.commit()
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/tuning", status_code=303)


@router.get("/tuning/runs/{run_id}")
def tuning_run_page(request: Request, run_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    from app.models.core import TuningRun, TuningRunPassage

    run = db.get(TuningRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    items = list(db.scalars(select(TuningRunPassage).where(TuningRunPassage.run_id == run_id).order_by(TuningRunPassage.ordinal.asc()).limit(200)))

    profiles = list_profiles(db)
    default_profile = get_default_profile(db, actor=settings.operator_id)

    return templates.TemplateResponse(
        request,
        "tuning_run.html",
        {
            "run": run,
            "items": items,
            "summary": run.summary_json or {},
            "profiles": profiles,
            "default_profile_id": default_profile.profile_id,
        },
    )
