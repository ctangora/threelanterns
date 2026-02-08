# Three Lanterns Milestone 3 Plan

## Baseline (Starting Point)
- Milestone 2 backend + internal curation UI is implemented and running locally.
- Stabilization is complete: review pages no longer 500 on datetime serialization, queue pagination is in place, launcher health checks are added, and regression tests pass.
- Current production-like mode remains local-first (`api` + `worker`) with `OPERATOR_ID` attribution and audit trails.

## Milestone 3 Objective
Move from MVP validation to sustained real-corpus intake and curation throughput:
- Ingest and curate a larger real corpus (target: 100 sources).
- Improve parser coverage and ingestion reliability.
- Increase reviewer throughput with better queue controls and bulk actions.
- Add internal search/export capabilities for research handoff.
- Keep governance strict: rights/provenance gates, evidence traceability, and auditable decisions.

## Scope

### In Scope
- Intake scaling from 25-source pilot to 100-source operational batch.
- Parser expansion for real-world formats (`pdf`, `docx`, `rtf`) in addition to existing types.
- Duplicate/witness handling, richer ingestion diagnostics, and dead-letter recovery tooling.
- AI proposal hardening in real-API mode (`USE_MOCK_AI=false`) with strict trace persistence.
- Reviewer workflow improvements: filtering, sorting, pagination continuity, bulk decisions.
- Internal search and export interfaces for approved artifacts.
- Monitoring and operator metrics for daily curation operations.

### Out of Scope
- Public-facing UI.
- Multi-user auth/RBAC.
- External connector implementations (interfaces may be extended only).
- Cloud deployment hardening.

## Success Metrics (Definition of Success)
- `>=100` sources registered in milestone corpus batch.
- `>=90%` ingestion success rate without manual code intervention.
- `0` server errors across `/review/*` routes during normal use.
- `>=500` passage review decisions completed with full audit trail.
- `100%` approved items include evidence links and traceable review decision.
- `100%` write/review transitions attributed to `OPERATOR_ID`.

## Locked Technical Decisions
- Continue with FastAPI + SQLAlchemy + server-rendered internal UI.
- Keep relational core + JSON fields for flexible metadata.
- Keep filesystem artifacts and DB metadata split.
- Keep DB-backed worker with retry/dead-letter behavior.
- Keep additive API evolution (no breaking route/path changes in M3).
- Keep canonical normalized comparison language as English for cross-corpus matching.

## Required Changes by Workstream

### 1) Intake Expansion and Parser Reliability
#### Goals
- Support additional input formats used in actual intake corpus.
- Improve parser observability and operator remediation for failures.

#### Code Changes
- Add parser modules:
  - `app/services/parsers/pdf.py`
  - `app/services/parsers/docx.py`
  - `app/services/parsers/rtf.py`
- Extend parser dispatch and validation:
  - `app/services/parsers/__init__.py`
  - `app/services/intake.py`
  - `app/services/workflows/ingestion.py`
- Extend settings for parser limits/timeouts:
  - `app/config.py`
  - `.env.example`
- Add parser dependencies in `pyproject.toml` (library choices finalized in implementation task).

#### Data/Migration Changes
- Add ingestion diagnostics fields (per-job):
  - `error_code`, `error_context_json`, `parser_name`, `parser_version`
- Add source-level fingerprint fields for duplicate detection:
  - `source_sha256`, `normalized_text_sha256`
- Add migration:
  - `migrations/002_m3_intake_scale.sql`
  - update `scripts/migrate.py`

#### Acceptance Checks
- Every supported extension round-trips through ingest pipeline.
- Parse failures produce actionable error codes and do not crash worker loop.

### 2) Duplicate Detection and Witness Linking
#### Goals
- Prevent duplicate records from repeated source intake.
- Preserve alternate witness relationships where duplicates are intentional.

#### Code Changes
- Add duplicate detection service:
  - `app/services/dedupe.py`
- Integrate dedupe checks into registration and ingestion:
  - `app/services/intake.py`
  - `app/services/workflows/ingestion.py`
- Extend record retrieval views to surface witness links:
  - `app/services/records.py`
  - `app/templates/record.html`

#### API Changes (Additive)
- `POST /api/v1/intake/register`:
  - Return duplicate/witness resolution metadata.
- New optional endpoint:
  - `POST /api/v1/intake/register/batch` for manifest-based registration with duplicate summary.

#### Acceptance Checks
- Re-registering same source hash does not create duplicate canonical records.
- Intentional alternate witnesses are linked and auditable.

### 3) AI Proposal Reliability and Trace Governance
#### Goals
- Improve proposal consistency for tags/links/flags with strict schema enforcement.
- Make proposal lifecycle fully auditable for quality review.

#### Code Changes
- Harden structured output and retry/repair:
  - `app/services/ai/proposals.py`
- Persist richer trace metadata:
  - `app/models/core.py` (`ProposalTrace` columns via migration)
  - `app/services/workflows/ingestion.py`
- Add policy checks for required evidence IDs before persist:
  - `app/services/validation.py`

#### Acceptance Checks
- Malformed AI outputs are retried/repaired or explicitly failed with trace.
- No tag/link/flag proposal is persisted without evidence linkage.

### 4) Review Throughput and Curation Ergonomics
#### Goals
- Let operators process higher review volume safely.
- Improve queue control without sacrificing audit/compliance.

#### Code Changes
- Add server-side queue filters/sorting:
  - `app/services/review.py`
  - `app/api/routes/review.py`
  - `app/web/routes.py`
  - `app/templates/review_list.html`
- Add bulk review action endpoint + form flow:
  - `POST /api/v1/review/bulk`
  - `POST /review/{kind}/bulk`
- Add lightweight review metrics:
  - `GET /api/v1/review/metrics`
  - optional `/review/metrics` internal page

#### Rules
- `reject` and `needs_revision` continue to require rationale.
- Bulk decisions emit one `ReviewDecision` + one `AuditEvent` per object.

#### Acceptance Checks
- Queue filtering/sorting works for passages/tags/links/flags.
- Bulk approve/reject updates states and emits complete audit trails.

### 5) Internal Search and Export for Research Handoff
#### Goals
- Enable fast lookup of curated material and export for downstream research.

#### Code Changes
- Add simple internal search service:
  - `app/services/search.py`
- Add search endpoints/routes:
  - `GET /api/v1/search`
  - `GET /search`
- Add export endpoints:
  - `GET /api/v1/exports/passages.csv`
  - `GET /api/v1/exports/tags.csv`
  - `GET /api/v1/exports/links.csv`
  - `GET /api/v1/exports/flags.csv`
- Optional artifact export command:
  - `scripts/export_curated.py`

#### Acceptance Checks
- Search returns deterministic results by query + filters.
- Export files contain only approved or explicitly requested states.

### 6) Operations, Monitoring, and Recovery
#### Goals
- Improve run-time visibility and reduce operator friction.

#### Code Changes
- Extend health detail output:
  - `GET /health/details` with DB, queue depth, worker heartbeat.
- Add daily summary command:
  - `scripts/daily_m3_report.py`
- Add dead-letter recovery tooling:
  - `scripts/requeue_dead_letter.py`
- Update launch/ops docs:
  - `README.md`
  - `docs/three-lanterns/milestone-3-runbook.md`

#### Acceptance Checks
- Operator can detect stalled worker and queue buildup quickly.
- Dead-letter jobs can be requeued with reason attribution.

## Public API Changes (Milestone 3 Additions)
- `GET /api/v1/review/queue`:
  - add optional filters: `state`, `source_id`, `min_confidence`, `sort_by`, `sort_dir`.
- `POST /api/v1/review/bulk`:
  - payload: object type, object IDs, decision, notes.
- `GET /api/v1/review/metrics`:
  - backlog counts, decision throughput, average queue age.
- `GET /api/v1/search`:
  - query text + optional filters (`object_type`, `tag`, `culture_region`, `review_state`).
- `GET /api/v1/exports/*`:
  - CSV exports for approved curated objects.

All new API behavior is additive to preserve backward compatibility with Milestone 2 clients.

## Data and Migration Plan
1. Create `migrations/002_m3_intake_scale.sql` with additive schema updates.
2. Update `scripts/migrate.py` to include migration ordering.
3. Backfill new nullable fields for existing rows.
4. Add indexes for review filters/search (state, created_at, source_id, confidence).
5. Verify migration on current local dataset before running larger intake batch.

## Testing Strategy

### Unit Tests
- Parser-specific tests for `pdf`, `docx`, `rtf`.
- Dedupe hash and witness-linking logic.
- Search ranking/filter behavior.
- Bulk review validation rules.

### API Tests
- New endpoints (`review/bulk`, `review/metrics`, `search`, `exports`).
- Queue filter/sort combinations.
- Duplicate registration behavior.

### Integration Tests
- End-to-end 100-source batch simulation with retries/dead-letter handling.
- Proposal trace enforcement under malformed AI output scenarios.
- Bulk review cycle with audit verification.

### Regression Requirements
- Preserve existing milestone 2 and stabilization tests.
- Continue enforcing no 500s on `/review/*`.

## Milestone 3 Acceptance Checklist
- [ ] Parser coverage includes `txt`, `md`, `html`, `epub`, `gz`, `pdf`, `docx`, `rtf`.
- [ ] 100-source intake batch can be registered and queued.
- [ ] Ingestion success rate is at least 90%.
- [ ] Duplicate detection prevents duplicate canonical rows.
- [ ] Review queue supports filters/sorting and bulk decisions.
- [ ] Bulk decisions generate per-object review + audit entries.
- [ ] Internal search endpoint and page are operational.
- [ ] Export endpoints generate valid CSV for curated objects.
- [ ] Health detail and daily summary tooling are operational.
- [ ] Full test suite passes with new M3 coverage.

## Execution Sequence (Recommended)
1. Schema + migration foundation.
2. Parser expansion + ingestion diagnostics.
3. Duplicate/witness handling.
4. AI trace hardening + validation gates.
5. Review throughput features (filters/bulk/metrics).
6. Search/export capabilities.
7. Ops tooling and final acceptance run.

## Risks and Mitigations
- Parser quality variability across PDF/RTF:
  - Mitigation: parser confidence flags + explicit fallback error codes.
- Review queue overload:
  - Mitigation: bulk actions, filters, backlog metrics.
- AI output drift:
  - Mitigation: strict schema validation, retry/repair, trace auditing.
- Corpus rights ambiguity:
  - Mitigation: preserve strict intake gate and provenance/rights requirement before ingest.

## Deliverables
- `docs/three-lanterns/milestone-3-plan.md` (this document)
- `docs/three-lanterns/milestone-3-runbook.md` (to create during implementation)
- `docs/three-lanterns/milestone-3-acceptance.md` (to create during implementation)

