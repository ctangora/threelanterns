# Three Lanterns Milestone 3 Acceptance

## Release Scope
Milestone 3 includes:
- R3A intake scale and reliability
- R3B curation throughput and research handoff interfaces

## R3A Acceptance Checklist
- [ ] `migrations/002_m3_intake_scale.sql` applies successfully.
- [ ] `source_material_records` includes dedupe/witness fields.
- [ ] `ingestion_jobs` includes parser and error diagnostics fields.
- [ ] `proposal_traces` includes retry/failure metadata.
- [ ] Supported parser set includes `txt/md/html/epub/gz/pdf/docx/rtf`.
- [ ] Duplicate registration prevents duplicate canonical records.
- [ ] Alternate witnesses link to canonical source via witness metadata.
- [ ] AI malformed output retry (single repair attempt) is traceable.
- [ ] Invalid evidence-linked proposals are blocked from persistence.
- [ ] Health details endpoint reports DB + queue + worker activity.

## R3B Acceptance Checklist
- [ ] Review queue supports filters (`state`, `source_id`, `min_confidence`) and sort options.
- [ ] Bulk review endpoint supports `passage`, `tag`, `link`, `flag`.
- [ ] Bulk review enforces notes for `reject` and `needs_revision`.
- [ ] Review metrics endpoint reports backlog and 24h throughput.
- [ ] Search endpoint and UI route are functional with filters.
- [ ] Export endpoints produce CSV payloads for passages/tags/links/flags.
- [ ] Review pages continue to render with zero internal server errors.
- [ ] Audit and `OPERATOR_ID` attribution remain intact for all write/review actions.

## R3.1 Translation Quality Acceptance Checklist
- [ ] Every `passage_evidence` row has modern-English `excerpt_normalized`.
- [ ] `passage_evidence` tracks translation quality fields:
  - `translation_status`
  - `detected_language_code`
  - `detected_language_label`
  - `language_detection_confidence`
  - `untranslated_ratio`
  - `needs_reprocess`
  - `reprocess_count`
- [ ] Auto reprocess queueing is active when `untranslated_ratio > 0.20`.
- [ ] Manual reprocess is available in API/UI.
- [ ] Reprocess max-attempt behavior marks passage `unresolved` after 2 failed quality attempts.
- [ ] Curated free-source lookups are allowlist-only (Wikisource, Internet Archive, Gutendex).
- [ ] Reprocess provenance is captured in `passage_translation_revisions`.
- [ ] Passage CSV export includes translation quality columns.

## R3.2 Quality Gating and Reprocess UX Checklist
- [ ] Reprocess Jobs page supports manual refresh and auto-refresh (`off|10s|30s|60s`).
- [ ] Reprocess queue supports `reason_code` filtering in API and UI.
- [ ] Manual reprocess action uses standardized reason codes + optional notes.
- [ ] Every passage has `usability_score`, `relevance_score`, and `relevance_state`.
- [ ] Passage relevance policy active:
  - `accepted >= 0.50`
  - `borderline 0.30-0.49`
  - `filtered < 0.30`
- [ ] Filtered passages are hidden by default in passage review queue and skipped for AI proposals.
- [ ] Auto-reprocess triggers on either:
  - `untranslated_ratio > 0.20`
  - `usability_score < 0.60`
- [ ] Reprocess reason summary endpoint returns grouped counts by reason/status.

## Automated Test Expectations
- [ ] Unit tests cover parser and proposal validation additions.
- [ ] API tests cover:
  - batch intake registration and dedupe outcomes
  - review queue filter/sort behavior
  - bulk review policy and processing
  - search/export routes
  - health details route
- [ ] Integration tests cover:
  - job diagnostics on parser/source failures
  - proposal trace retry/failure metadata
  - end-to-end ingestion -> review -> export path

## Operational Gate Targets
- [ ] Intake volume gate: 100 sources registered/queued.
- [ ] Ingestion reliability gate: >=90% completion without code changes.
- [ ] Curation reliability gate: zero `/review/*` 500s in smoke run.
- [ ] Throughput gate: review metrics endpoint active and reporting.

## Deferred to Release 4
- OCR for scanned/image PDFs.
- External ingestion connectors beyond local corpus.
- Public UI and user auth/RBAC.
- Cloud deployment hardening.
