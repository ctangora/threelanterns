# Three Lanterns Validation and Acceptance (Phase 1)

## Purpose
Define executable-style test scenarios, quality gates, review service levels, and milestone acceptance checks for the Phase 1 documentation handoff.

## Data-Quality Gates
Objects cannot advance to publish-ready state unless all gates pass:

1. Schema gate
- Required fields present.
- Types and enum values valid.

2. Rights and provenance gate
- `rights_status` present and valid.
- `rights_evidence` present.
- Provenance summary is non-empty.

3. Evidence integrity gate
- All tag/link/flag claims include one or more valid evidence IDs.
- Every evidence ID resolves to an existing `PassageEvidence` record.

4. Vocabulary gate
- All ontology terms are from approved controlled lists or routed to pending-vocab workflow.

5. Review gate
- Human review decision `approve` required before any object may become publish-eligible.

6. Audit gate
- Create, update, review, and publish actions emit complete audit events.

## Executable-Style Test Scenarios

### T01: Ingestion rejects missing core identity
Given a `TextRecord` without `text_id`  
When schema validation runs  
Then ingest fails with `required_field_missing` and record remains blocked.

### T02: Ingestion rejects missing rights/provenance
Given a `TextRecord` with no `rights_status` or `provenance_summary`  
When rights/provenance gate runs  
Then record fails gate and cannot reach review queue.

### T03: Vocabulary rejection routes term to governance queue
Given a `RitualPatternTag` with unknown `controlled_term`  
When vocabulary gate runs  
Then tag is blocked, pending-vocab item is created, and no publish eligibility is granted.

### T04: Passage evidence requires resolvable span and language metadata
Given a `PassageEvidence` missing `source_span_locator` or `original_language`  
When evidence validation runs  
Then record fails and does not persist as approved evidence.

### T05: Commonality link requires score, relation type, and evidence
Given a `CommonalityLink` missing `weighted_similarity_score`, `relation_type`, or `evidence_ids`  
When link validation runs  
Then record is rejected with explicit field-level error details.

### T06: Flag traceability requires rationale and evidence links
Given a `FlagRecord` with empty rationale or no evidence IDs  
When flag validation runs  
Then record fails with `flag_traceability_error` and remains blocked.

### T07: Multilingual consistency enforces normalized and original fields
Given a `PassageEvidence` with original excerpt but missing normalized excerpt  
When multilingual consistency validation runs  
Then evidence fails and cannot be used for link scoring.

### T08: Review gate prevents publishing without approval
Given an object in `proposed` state with no `ReviewDecision` of `approve`  
When publish assembly runs  
Then object remains non-publishable and stays blocked.

### T09: Audit enforcement on create/update/review
Given object create, update, and review operations  
When audit validation runs  
Then each operation must include actor, action, object ID, and timestamp or operation is invalid.

### T10: Referential integrity enforcement
Given a `SourceMaterialRecord` pointing to nonexistent `text_id`  
When referential validation runs  
Then source record is rejected and assigned correction task.

## Review Service Levels (SLA Targets)
- Initial review triage: within 2 business days of queue entry.
- Standard object review (`passage`, `tag`, `flag`): within 5 business days.
- Complex link review (`CommonalityLink` with medium confidence): within 7 business days.
- Critical flag escalation (`severity=critical`): within 1 business day.

## Review Decision Policies
1. `approve`: object may move to publish eligibility if dependencies also pass.
2. `reject`: object remains blocked and requires replacement or closure.
3. `needs_revision`: object returns to proposal stage with required revision notes.

## Documentation Consistency Checks
Before Phase 1 closure:
1. All seven required artifacts exist in target paths.
2. Field names are consistent across data dictionary, workflows, and template appendix.
3. Workflow state names are consistent across all docs.
4. Flag types and relation types match canonical contracts.

## Milestone 1 Acceptance Checklist
- [ ] Seven Phase 1 artifacts are present.
- [ ] Data dictionary covers all seven core records with required fields and constraints.
- [ ] Ritual ontology includes dimensions, controlled terms, and scoring guidance.
- [ ] Workflow pseudocode covers acquisition through publish plus error handling and audit.
- [ ] Validation suite defines at least eight executable-style scenarios.
- [ ] Corpus strategy includes global balancing rubric and pilot list schema for 50-100 texts.
- [ ] Locked decisions from scope document are reflected in all downstream artifacts.
