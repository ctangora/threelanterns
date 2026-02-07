# Three Lanterns Phase 1: Corpus Strategy

## Purpose
Define a pilot corpus of 50-100 texts that is globally balanced, legally ingestible, and suitable for passage-level cross-cultural ritual comparison.

## Pilot Size and Composition
- Target size: 50-100 texts.
- Preferred baseline: 72 texts (12 per region group) for balanced startup.
- Unit of cataloging: one canonical text record may reference multiple witnesses/editions.

## Global Balancing Rubric
Each candidate text receives weighted scores:

1. Regional Representation (0-5)
- 5: materially improves coverage in underrepresented region.
- 3: maintains already represented region.
- 0: redundant overrepresentation.

2. Temporal Spread (0-5)
- 5: adds a period gap not yet covered.
- 3: adds depth to existing period.
- 0: duplicate period with minimal value.

3. Ritual Density (0-5)
- 5: high concentration of procedural ritual descriptions.
- 3: mixed descriptive and doctrinal content.
- 0: little usable ritual evidence.

4. Provenance Quality (0-5)
- 5: strong citation trail, stable repository, clear witness context.
- 3: partial provenance with recoverable gaps.
- 0: uncertain source origin.

5. Linguistic Utility (0-5)
- 5: adds language family not in corpus and has viable processing path.
- 3: already covered language but significant content.
- 0: inaccessible language format for current workflow.

6. Comparative Utility (0-5)
- 5: likely to contribute to cross-tradition ritual pattern links.
- 3: useful standalone context.
- 0: isolated with low comparability.

Inclusion threshold:
- Include if total score >= 20 and Provenance Quality >= 3.
- Manually review candidates scoring 16-19 if they fill major regional gaps.

## Region Group Targets (Example Allocation)
- Africa and Nile corridor: 8-14 texts.
- West and Central Asia: 8-14 texts.
- South Asia: 8-14 texts.
- East Asia: 8-14 texts.
- Europe and Mediterranean: 8-14 texts.
- Americas and Indigenous records: 8-14 texts.

## Rights and Provenance Rules

### Inclusion Rules
1. Legal-only boundary:
- Public-domain texts are eligible.
- Licensed materials are eligible if license allows ingestion and citation.
2. Every text must include:
- Rights status.
- Source repository reference.
- Citation or accession information.
- Provenance summary.
3. Every passage claim must map to a source span locator.

### Exclusion Rules
- No ingest without legal basis.
- No ingest if citation chain is missing and cannot be repaired.
- No publish-ready record if provenance fields fail validation.

## Required Metadata at Intake
Minimum fields at source intake:
- Candidate ID
- Canonical title (or best-known title)
- Region group
- Tradition tags (provisional allowed)
- Date range (provisional allowed with confidence)
- Source repository
- Rights status
- Provenance note
- Language set
- Witness type (manuscript, print, inscriptional, compiled account)

## Source Intake Checklist
1. Confirm legal basis (`public_domain` or license identifier).
2. Capture source URL or archival reference.
3. Capture holding institution and accession/citation.
4. Record edition/witness type and date estimate.
5. Capture language metadata and script if known.
6. Mark ingestion confidence (`high`, `medium`, `low`).
7. Open unresolved issues ticket for missing required fields.

## Pilot Text List Structure
Use this row template for candidate tracking:

| field | description |
| --- | --- |
| candidate_id | stable draft identifier |
| canonical_title | normalized title |
| alt_titles | semicolon-delimited alternatives |
| region_group | one of six region groups |
| tradition_tags | provisional controlled terms |
| date_start | estimated earliest year |
| date_end | estimated latest year |
| date_confidence | high/medium/low |
| language_set | one or more language codes |
| rights_status | public_domain/licensed/restricted |
| rights_evidence | citation to legal basis |
| source_repository | library/archive/source database |
| accession_or_citation | manuscript shelfmark, DOI, catalog ID, or bibliographic ref |
| witness_type | manuscript/printed/inscriptional/compiled |
| ritual_density_score | 0-5 |
| comparative_utility_score | 0-5 |
| provenance_quality_score | 0-5 |
| selection_decision | include/review/exclude |
| decision_note | concise reason |

## Corpus Completion Exit Criteria
Pilot corpus is ready for milestone 2 implementation planning when:
1. 50-100 records pass rights and provenance validation.
2. All six region groups are represented.
3. At least 70 percent of texts have medium or high date confidence.
4. At least 85 percent of included texts have required metadata complete.
5. All inclusion decisions have logged rationale.
