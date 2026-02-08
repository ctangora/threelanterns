# Three Lanterns Milestone 3 Runbook

## Purpose
Operate Release 3 locally for scaled intake, review throughput, and research handoff export.

## Prerequisites
- Python 3.12+
- PostgreSQL 16 (release acceptance path) or local SQLite for development
- OpenAI API key
- Corpus files under `__Reference__/`

## Environment Setup
1. Copy `.env.example` to `.env`.
2. Required:
   - `DATABASE_URL`
   - `OPENAI_API_KEY`
   - `OPERATOR_ID`
3. Recommended for development:
   - `USE_MOCK_AI=true`
4. Required for release acceptance:
   - `USE_MOCK_AI=false`

## Install
```bash
python3 -m pip install -e ".[dev]"
```

## Migrate
```bash
python3 scripts/migrate.py
```

## Run Services
```bash
uvicorn app.main:app --reload
python3 -m app.workers.run_worker
```

## Key Health and Queue Checks
1. `GET /health` returns `ok`.
2. `GET /health/details` reports:
   - `database_ok=true`
   - queue depth by status
   - worker last activity timestamp
3. `GET /api/v1/review/metrics` reports backlog and 24h throughput.

## Intake Operations

### One Source
1. Register source:
   - `POST /api/v1/intake/register`
2. Queue ingest:
   - `POST /api/v1/jobs/ingest`

### Batch Registration
1. Submit `POST /api/v1/intake/register/batch` with `items[]`.
2. Confirm summary counts:
   - `created`
   - `exact_duplicates`
   - `alternate_witnesses`
   - `failed`

### R3A Scale Run (up to 100)
```bash
python3 scripts/run_r3a_cycle.py
```

## Review Operations
1. Use queue API/UI filters:
   - `state`
   - `source_id` (passages)
   - `needs_reprocess`
   - `max_untranslated_ratio`
   - `detected_language`
   - `min_confidence`
   - `sort_by`, `sort_dir`
2. Single-item decision:
   - `POST /api/v1/review/{object_type}/{object_id}`
3. Bulk decisions:
   - `POST /api/v1/review/bulk`
4. Reject/needs_revision decisions require notes in both single and bulk flows.

## Translation Quality and Reprocess Operations
1. Passage quality inspection:
   - `GET /api/v1/passages/{passage_id}/quality`
2. Manual reprocess:
   - API: `POST /api/v1/passages/{passage_id}/reprocess`
   - Web: `/review/passages` using the per-passage "Queue Reprocess" form
3. Reprocess queue visibility:
   - API: `GET /api/v1/reprocess/jobs`
   - Web: `/review/reprocess-jobs`
4. Auto policy:
   - `untranslated_ratio > 0.20` auto-queues reprocess
   - max attempts: 2, then passage is marked `unresolved`
   - unresolved passages emit `uncertain_translation` flag

## Search and Export
1. Internal search:
   - API: `GET /api/v1/search`
   - UI: `/search`
2. CSV exports:
   - `/api/v1/exports/passages.csv`
   - `/api/v1/exports/tags.csv`
   - `/api/v1/exports/links.csv`
   - `/api/v1/exports/flags.csv`

## Dead-Letter Recovery
Requeue all dead-letter jobs:
```bash
python3 scripts/requeue_dead_letter.py --all --reason "parser fix deployed"
```

Requeue one job:
```bash
python3 scripts/requeue_dead_letter.py --job-id <job_id> --reason "manual retry"
```

## Daily Reporting
```bash
python3 scripts/daily_m3_report.py
```

Expected output:
- source and passage totals
- job counts by status
- review backlog and throughput metrics
