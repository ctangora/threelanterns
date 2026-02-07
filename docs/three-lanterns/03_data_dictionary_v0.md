# Three Lanterns Data Dictionary v0

## Purpose
Define canonical record contracts, validation constraints, controlled vocabularies, and referential rules for Phase 1 handoff.

## Conventions
- Record identifiers are immutable once issued.
- `required` means record fails validation if absent.
- `enum` values are controlled terms.
- Confidence scores are numeric values from 0.00 to 1.00 unless otherwise stated.
- Timestamps use ISO-8601 UTC format.

## Core Record Types

### 1) `TextRecord`
Represents a canonical text-level entity.

| field | type | required | constraints |
| --- | --- | --- | --- |
| text_id | string | yes | unique, immutable |
| canonical_title | string | yes | non-empty |
| alternate_titles | array<string> | no | may be empty |
| origin_culture_region | enum | yes | must exist in `region_vocabulary` |
| tradition_tags | array<string> | yes | each term in `tradition_vocabulary` |
| date_range_start | integer | no | <= `date_range_end` if present |
| date_range_end | integer | no | >= `date_range_start` if present |
| date_confidence | enum | yes | `high`, `medium`, `low`, `unknown` |
| language_set | array<string> | yes | each in `language_vocabulary` |
| rights_status | enum | yes | `public_domain`, `licensed`, `restricted` |
| provenance_summary | string | yes | non-empty, citation-grade summary |
| source_count | integer | no | derived, >= 0 |
| record_status | enum | yes | `draft`, `in_review`, `approved`, `published` |

### 2) `SourceMaterialRecord`
Represents witness-level source information for a text.

| field | type | required | constraints |
| --- | --- | --- | --- |
| source_id | string | yes | unique, immutable |
| text_id | string | yes | FK -> `TextRecord.text_id` |
| holding_institution | string | yes | non-empty |
| accession_or_citation | string | yes | non-empty |
| edition_witness_type | enum | yes | `manuscript`, `printed`, `inscriptional`, `compiled_account`, `translation` |
| acquisition_method | enum | yes | `archive_scan`, `repository_download`, `manual_transcription`, `partner_transfer` |
| digitization_status | enum | yes | `not_started`, `in_progress`, `complete`, `failed` |
| source_language | string | no | in `language_vocabulary` |
| source_url_or_locator | string | no | URL or archive locator |
| rights_evidence | string | yes | legal basis note |
| source_provenance_note | string | yes | non-empty |

### 3) `PassageEvidence`
Represents a passage used as evidence for tags, links, and flags.

| field | type | required | constraints |
| --- | --- | --- | --- |
| passage_id | string | yes | unique, immutable |
| text_id | string | yes | FK -> `TextRecord.text_id` |
| source_id | string | yes | FK -> `SourceMaterialRecord.source_id` |
| source_span_locator | string | yes | must resolve to source section/page/line span |
| excerpt_original | string | yes | non-empty |
| excerpt_normalized | string | yes | non-empty |
| original_language | string | yes | in `language_vocabulary` |
| normalized_language | string | yes | in `language_vocabulary` |
| extraction_confidence | number | yes | 0.00-1.00 |
| reviewer_state | enum | yes | `proposed`, `approved`, `rejected`, `needs_revision` |
| publish_state | enum | yes | `blocked`, `eligible`, `published` |

### 4) `RitualPatternTag`
Represents ontology-based ritual tagging at passage level.

| field | type | required | constraints |
| --- | --- | --- | --- |
| tag_id | string | yes | unique, immutable |
| ontology_dimension | enum | yes | in `ontology_dimension_vocabulary` |
| controlled_term | string | yes | in dimension term list |
| confidence | number | yes | 0.00-1.00 |
| evidence_ids | array<string> | yes | each FK -> `PassageEvidence.passage_id` |
| proposer_type | enum | yes | `automated`, `human` |
| reviewer_state | enum | yes | `proposed`, `approved`, `rejected`, `needs_revision` |
| rationale_note | string | no | optional explanation |

### 5) `CommonalityLink`
Represents cross-record relationship and similarity claims.

| field | type | required | constraints |
| --- | --- | --- | --- |
| link_id | string | yes | unique, immutable |
| source_entity_type | enum | yes | `text`, `passage`, `tag` |
| source_entity_id | string | yes | FK based on source entity type |
| target_entity_type | enum | yes | `text`, `passage`, `tag` |
| target_entity_id | string | yes | FK based on target entity type |
| relation_type | enum | yes | `isVersionOf`, `isRelatedTo`, `sharesPatternWith`, `isDerivativeOf` |
| weighted_similarity_score | number | yes | 0.00-1.00 |
| evidence_ids | array<string> | yes | one or more FK -> `PassageEvidence.passage_id` |
| reviewer_decision | enum | yes | `proposed`, `approved`, `rejected`, `needs_revision` |
| decision_note | string | no | optional reviewer rationale |

### 6) `FlagRecord`
Represents uncertainty and source-bias warnings tied to evidence.

| field | type | required | constraints |
| --- | --- | --- | --- |
| flag_id | string | yes | unique, immutable |
| object_type | enum | yes | `text`, `source`, `passage`, `tag`, `link` |
| object_id | string | yes | FK to object_type target |
| flag_type | enum | yes | `uncertain_translation`, `hostile_source_frame`, `provenance_gap`, `date_uncertainty`, `conflicting_witnesses` |
| severity | enum | yes | `low`, `medium`, `high`, `critical` |
| rationale | string | yes | non-empty |
| evidence_ids | array<string> | yes | one or more FK -> `PassageEvidence.passage_id` |
| reviewer_state | enum | yes | `proposed`, `approved`, `rejected`, `needs_revision` |

### 7) `ReviewDecision`
Represents human validation actions.

| field | type | required | constraints |
| --- | --- | --- | --- |
| review_id | string | yes | unique, immutable |
| object_type | enum | yes | `passage`, `tag`, `link`, `flag`, `text`, `source` |
| object_id | string | yes | FK by object_type |
| reviewer_id | string | yes | non-empty |
| decision | enum | yes | `approve`, `reject`, `needs_revision` |
| decision_timestamp | datetime | yes | ISO-8601 UTC |
| notes | string | no | optional |
| previous_state | string | no | lifecycle trace |
| new_state | string | no | lifecycle trace |

## Controlled Vocabularies

### `region_vocabulary`
- `africa_nile`
- `west_central_asia`
- `south_asia`
- `east_asia`
- `europe_mediterranean`
- `americas_indigenous`

### `tradition_vocabulary` (starter set)
- `celtic`
- `greek_mystery`
- `zoroastrian`
- `grimoire_tradition`
- `mesopotamian_ritual`
- `vedic_ritual`
- `daoist_ritual`
- `yoruba_orisha`
- `andean_ritual`
- `mesoamerican_ritual`
- `early_jewish_apocalyptic`
- `late_antique_esoteric`

### `ontology_dimension_vocabulary`
- `ritual_intent`
- `ritual_actors`
- `ritual_actions`
- `materials_tools`
- `time_timing`
- `location_setting`
- `invocation_structure`
- `exchange_offering`
- `protection_boundary`
- `divination_modality`
- `outcome_claim`

### `language_vocabulary`
Language terms must use project-approved language code list.  
Minimum startup list includes commonly expected corpus languages and can expand through governance workflow.

## Referential Constraints
1. `SourceMaterialRecord.text_id` must resolve to existing `TextRecord`.
2. `PassageEvidence.text_id` and `PassageEvidence.source_id` must both resolve and be compatible.
3. Every `RitualPatternTag.evidence_ids` entry must resolve to existing `PassageEvidence`.
4. Every `CommonalityLink.evidence_ids` entry must resolve to existing `PassageEvidence`.
5. Every `FlagRecord.evidence_ids` entry must resolve to existing `PassageEvidence`.
6. `ReviewDecision.object_id` must resolve according to `object_type`.

## Validation Rules
1. Required-field rule: any missing required field fails ingest.
2. Enum rule: enum values outside controlled vocab fail ingest or route to governed pending queue.
3. Confidence rule: score fields must be in range 0.00-1.00.
4. Evidence-link rule: tags, links, and flags must include at least one evidence reference.
5. Rights rule: `rights_status` plus `rights_evidence` required before record can move to `approved`.
6. Publish gate rule: no object may become `published` unless associated review decision is `approve`.
7. Traceability rule: changes to reviewed objects require review trail entries.

## Record Lifecycle States
- Draft objects begin in `proposed` or `draft`.
- Human review determines `approved`, `rejected`, or `needs_revision`.
- Publish eligibility is blocked unless approval exists and required dependencies pass validation.

## Governance Notes
- Controlled vocabulary additions require explicit review decision entry.
- Deprecated terms remain resolvable for historical compatibility but are blocked for new tagging.
