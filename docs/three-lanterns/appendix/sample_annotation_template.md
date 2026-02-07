# Three Lanterns Appendix: Sample Annotation Template

## Purpose
Provide a standard template for passage-level evidence annotation and downstream tag/link/flag proposals.

## Template

```text
ANNOTATION_RECORD
  annotation_id: <string>
  text_id: <string>
  source_id: <string>
  source_span_locator: <string>   # page/line/section reference

  excerpt_original:
    language: <language_code>
    text: <verbatim excerpt>

  excerpt_normalized:
    language: comparison_canonical
    text: <normalized translation for comparison>

  extraction_confidence: <0.00-1.00>
  reviewer_state: proposed

  ritual_pattern_tags:
    - ontology_dimension: <dimension_name>
      controlled_term: <approved_term>
      confidence: <0.00-1.00>
      rationale: <short reason>

  commonality_candidates:
    - target_entity_type: <text|passage|tag>
      target_entity_id: <string>
      relation_type: sharesPatternWith
      weighted_similarity_score: <0.00-1.00>
      supporting_evidence_ids: [<passage_id>, ...]
      rationale: <short reason>

  flags:
    - flag_type: <uncertain_translation|hostile_source_frame|provenance_gap|date_uncertainty|conflicting_witnesses>
      severity: <low|medium|high|critical>
      rationale: <short reason>
      evidence_ids: [<passage_id>, ...]

  reviewer_decision:
    decision: <approve|reject|needs_revision>
    reviewer_id: <string>
    notes: <optional notes>
    timestamp_utc: <ISO-8601 datetime>
```

## Example Record A (Passage Tagging)

```text
ANNOTATION_RECORD
  annotation_id: ann_0001
  text_id: txt_0012
  source_id: src_0041
  source_span_locator: "folio_14r:lines_03-17"

  excerpt_original:
    language: lat
    text: "..."

  excerpt_normalized:
    language: comparison_canonical
    text: "The officiant draws a boundary, names powers, and offers smoke before petition."

  extraction_confidence: 0.87
  reviewer_state: proposed

  ritual_pattern_tags:
    - ontology_dimension: protection_boundary
      controlled_term: circle_boundary
      confidence: 0.79
      rationale: "Explicit boundary drawing before invocation."
    - ontology_dimension: invocation_structure
      controlled_term: formulaic_epithet_sequence
      confidence: 0.74
      rationale: "Repeated formulaic naming pattern appears in sequence."

  commonality_candidates: []

  flags:
    - flag_type: uncertain_translation
      severity: medium
      rationale: "One key verb can also mean seal/mark depending on manuscript witness."
      evidence_ids: [psg_0039]

  reviewer_decision:
    decision: needs_revision
    reviewer_id: rev_curator_02
    notes: "Confirm alternate witness reading before approval."
    timestamp_utc: 2026-02-07T20:00:00Z
```

## Example Record B (Commonality Proposal)

```text
ANNOTATION_RECORD
  annotation_id: ann_0002
  text_id: txt_0033
  source_id: src_0075
  source_span_locator: "chapter_6:section_2"

  excerpt_original:
    language: grc
    text: "..."

  excerpt_normalized:
    language: comparison_canonical
    text: "The rite is performed at dawn with libation and repeated address to named powers."

  extraction_confidence: 0.91
  reviewer_state: proposed

  ritual_pattern_tags:
    - ontology_dimension: time_timing
      controlled_term: dawn_operation
      confidence: 0.88
      rationale: "Explicit dawn timing marker present."
    - ontology_dimension: exchange_offering
      controlled_term: liquid_libation
      confidence: 0.83
      rationale: "Ritual specifies poured liquid offering."

  commonality_candidates:
    - target_entity_type: passage
      target_entity_id: psg_0110
      relation_type: sharesPatternWith
      weighted_similarity_score: 0.77
      supporting_evidence_ids: [psg_0098, psg_0110]
      rationale: "Overlap in timing, offering mode, and invocation structure."

  flags:
    - flag_type: hostile_source_frame
      severity: low
      rationale: "Narrating source uses pejorative framing language."
      evidence_ids: [psg_0098]

  reviewer_decision:
    decision: approve
    reviewer_id: rev_curator_01
    notes: "Similarity acceptable with non-equivalence note."
    timestamp_utc: 2026-02-07T20:15:00Z
```

## Completion Rule
No annotation is publish-eligible unless:
1. Required fields are complete.
2. Evidence links resolve.
3. Review decision is `approve`.
