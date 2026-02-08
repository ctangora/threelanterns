# Three Lanterns Milestone 2 Acceptance

## Scope Confirmation
Milestone 2 delivers:
- Python FastAPI backend
- Internal server-rendered curation UI
- Relational core schema with flexible JSON fields
- DB-backed ingestion worker with retries/dead-letter
- Local filesystem artifact storage
- API-orchestrated proposal flow with trace logging
- Review workflow and audit trail

## Acceptance Checklist
- [ ] App starts with required env vars and fails fast if missing (`DATABASE_URL`, `OPENAI_API_KEY`, `OPERATOR_ID`).
- [ ] PostgreSQL schema migration executes successfully.
- [ ] Intake discover endpoint returns only eligible file extensions.
- [ ] 25 local text-ready sources can be discovered and queued.
- [ ] Ingestion worker processes queued jobs and writes passage evidence.
- [ ] Proposal traces are created for AI/heuristic proposal bundles.
- [ ] Review decisions enforce notes for `reject` and `needs_revision`.
- [ ] Audit events exist for create/update/review transitions.
- [ ] Passage publish eligibility remains blocked until approval.
- [ ] At least one end-to-end ingestion -> review flow passes integration tests.

## Implemented Automated Tests
Phase 1 gate scenarios:
- T01 missing rights/required identity input fails registration.
- T02 missing provenance input fails registration.
- T03 unknown ontology term routes to pending vocabulary queue.
- T04 passage missing required locator fails persistence.
- T05 invalid relation type fails validation.
- T06 empty flag rationale fails validation.
- T07 multilingual original + normalized fields validated after ingestion.
- T08 publish state blocked until human `approve`.
- T09 audit events emitted during create/review lifecycle.
- T10 foreign-key integrity enforced for source/job references.

M2 scenarios:
- Supported extension discovery validation.
- Job idempotency key reuse returns same job.
- Parser coverage (`txt`, `md`, `html`, `epub`, `gz`).
- Proposal trace persistence check.
- Worker retries to dead-letter after max attempts.
- End-to-end API + worker + review flow.

## Deferred to Milestone 2.1+
- PDF OCR toolchain and scanned-image extraction.
- External source connectors (interface exists, no concrete implementation).
- Public discovery UI.
- Multi-user auth and RBAC.
- Deployment hardening and production observability stack.

