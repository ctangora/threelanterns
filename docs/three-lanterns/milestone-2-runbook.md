# Three Lanterns Milestone 2 Runbook

## Purpose
Run the internal backend + curation MVP locally, process the 25 source tranche, and execute one full review cycle.

## Prerequisites
- Python 3.12+
- PostgreSQL 16 reachable via `DATABASE_URL`
- OpenAI API key set in `OPENAI_API_KEY`
- Local corpus present under `__Reference__/`

## Environment Setup
1. Copy `.env.example` to `.env`.
2. Set:
   - `DATABASE_URL`
   - `OPENAI_API_KEY`
   - `OPERATOR_ID`
3. Optional:
   - `USE_MOCK_AI=true` for deterministic local proposal generation.

## Install
```bash
python3 -m pip install -e ".[dev]"
```

## Database Migration
```bash
python3 scripts/migrate.py
```

## Start API
```bash
uvicorn app.main:app --reload
```

## Start Worker
```bash
python3 -m app.workers.run_worker
```

## Internal UI Routes
- `/intake`
- `/jobs`
- `/review/passages`
- `/review/tags`
- `/review/links`
- `/review/flags`
- `/records/{id}`
- `/audit/{id}`

## API Routes
- `POST /api/v1/intake/discover`
- `POST /api/v1/intake/register`
- `POST /api/v1/jobs/ingest`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/review/queue`
- `POST /api/v1/review/{object_type}/{object_id}`
- `GET /api/v1/records/{object_type}/{object_id}`
- `GET /api/v1/audit/{object_type}/{object_id}`

## Milestone 2 Batch Run (25 Sources)
```bash
python3 scripts/run_m2_cycle.py
```

Expected behavior:
1. Discover exactly 25 local text-ready files (`txt/md/html/epub/gz`).
2. Register each source and queue ingestion jobs.
3. Worker processes jobs and creates passage/tag/link/flag proposals.

## Operational Checks
1. `GET /health` returns `ok`.
2. `/jobs` shows no stuck `running` jobs.
3. `/review/passages` contains proposed items.
4. Reviewing one passage to `approve` creates:
   - `ReviewDecision`
   - corresponding `AuditEvent`
   - passage `publish_state=eligible`.

## Failure Handling
- Parse failure: job returns to `pending` until `max_attempts`, then `dead_letter`.
- Bad AI output: fallback heuristic proposals are generated and traced.
- Missing note on reject/revision: review request is rejected with validation error.

