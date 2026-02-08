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

## Milestone 2 Implementation

### Install

```bash
python3 -m pip install -e ".[dev]"
```

### Configure

Copy `.env.example` to `.env` and set:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPERATOR_ID`

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

### Batch 25-source cycle

```bash
python3 scripts/run_m2_cycle.py
```
