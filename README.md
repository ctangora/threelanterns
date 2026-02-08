# Three Lanterns

This repository tracks the Three Lanterns project, an online database concept for preserving and comparing underrepresented ritual and belief texts.

## Phase 1 Research Brief Package

Start with the milestone handoff docs in `docs/three-lanterns/`:

- `docs/three-lanterns/01_mission_scope.md`
- `docs/three-lanterns/02_corpus_strategy.md`
- `docs/three-lanterns/03_data_dictionary_v0.md`
- `docs/three-lanterns/04_ritual_ontology_v0.md`
- `docs/three-lanterns/05_workflows_pseudocode.md`
- `docs/three-lanterns/06_validation_and_acceptance.md`
- `docs/three-lanterns/appendix/sample_annotation_template.md`

## Milestone 2 / Release 3 Implementation

### Install

```bash
python3 -m pip install -e ".[dev]"
```

### Configure

Copy `.env.example` to `.env` and set:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPERATOR_ID`
- Optional for R3 tuning:
  - `USE_MOCK_AI` (`true` for local dev, `false` for release acceptance)
  - `MAX_SOURCE_CHARS`
  - `MAX_PASSAGES_PER_SOURCE`
  - `MAX_REGISTER_FINGERPRINT_CHARS`
  - `PARSER_TIMEOUT_SECONDS`

### Migrate

```bash
python3 scripts/migrate.py
```

### Run API + Worker

```bash
uvicorn app.main:app --reload
python3 -m app.workers.run_worker
```

### macOS Click-To-Run

In Finder, double-click:

- `Start Three Lanterns UI.command`

This launches API + worker in the background (using local SQLite + mock AI defaults if env vars are unset) and opens:

- `http://127.0.0.1:8000/intake`

To stop both processes, double-click:

- `Stop Three Lanterns UI.command`

Troubleshooting:

1. If UI does not load, check `http://127.0.0.1:8000/health`.
2. If startup fails, inspect `.run/api.log` and `.run/worker.log`.
3. If you changed code, stop then restart via the two `.command` files.

### Internal UI

- `/intake`
- `/jobs`
- `/review/passages`
- `/review/tags`
- `/review/links`
- `/review/flags`
- `/review/reprocess-jobs`
- `/review/metrics`
- `/search`

### Internal API (Release 3 additions)

- `POST /api/v1/intake/register/batch`
- `GET /api/v1/review/metrics`
- `POST /api/v1/review/bulk`
- `GET /api/v1/search`
- `GET /api/v1/exports/passages.csv`
- `GET /api/v1/exports/tags.csv`
- `GET /api/v1/exports/links.csv`
- `GET /api/v1/exports/flags.csv`
- `GET /health/details`

### Release 3.1 Translation/Reprocess API

- `POST /api/v1/passages/{passage_id}/reprocess`
- `GET /api/v1/passages/{passage_id}/quality`
- `GET /api/v1/reprocess/jobs`

Passages now include:

- modern-English normalized text in `excerpt_normalized`
- translation quality metrics (`untranslated_ratio`, detected language, status)
- auto reprocess queueing when untranslated ratio exceeds `0.20`

### Batch 25-source cycle

```bash
python3 scripts/run_m2_cycle.py
```

### Release 3 Intake / Operations Scripts

R3A intake run (up to 100 local sources):

```bash
python3 scripts/run_r3a_cycle.py
```

Daily operations summary:

```bash
python3 scripts/daily_m3_report.py
```

Requeue dead-letter jobs with required rationale:

```bash
python3 scripts/requeue_dead_letter.py --all --reason "parser fix deployed"
```

```bash
python3 scripts/requeue_dead_letter.py --job-id job_123 --reason "manual retry"
```

### Release 3 Planning Docs

- `docs/three-lanterns/milestone-3-plan.md`
- `docs/three-lanterns/milestone-3-runbook.md`
- `docs/three-lanterns/milestone-3-acceptance.md`
