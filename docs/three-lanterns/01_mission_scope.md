# Three Lanterns Phase 1: Mission and Scope

## Mission
Three Lanterns preserves and compares underrepresented ritual and belief texts across cultures.  
Phase 1 creates a data-first research brief that enables later implementation of multilingual extraction, ritual pattern tagging, cross-cultural commonality mapping, and uncertainty/source-bias flagging.

## Product Intent
- Build a rigorous but accessible foundation for researchers and public readers.
- Identify ritual practices documented directly and indirectly (including hostile or back-handed accounts).
- Compare ritual structure across traditions to recover durable cross-cultural patterns.
- Preserve provenance and uncertainty so interpretation remains transparent.

## Primary Audience
1. Researchers: need citation-grade provenance, uncertainty markers, and reproducible links between claims and passages.
2. Public learners: need understandable summaries, browse paths, and clear context around confidence.

## Milestone 1 Deliverable Boundary
Phase 1 is documentation-only handoff material.

### In Scope
- Corpus definition for a 50-100 text globally balanced pilot.
- Data contracts for seven core record types.
- Controlled vocabularies and validation rules.
- Ritual ontology and cross-culture comparison dimensions.
- End-to-end workflow pseudocode from acquisition to publish-ready records.
- Validation scenarios, review service levels, and acceptance checklist.
- Annotation template and sample records for implementation handoff.

### Out of Scope
- Production database implementation.
- API, UI, deployment, and runtime operations.
- Automated ETL jobs or model training pipelines.
- Performance tuning and infrastructure sizing.

## Policy Defaults
- Inclusion boundary: legal-only (public-domain or appropriately licensed material may be ingested).
- First-class flags: uncertainty and source bias.
- Comparison unit: passage-level evidence.
- Language strategy: multilingual analysis from day one, with normalized fields to support cross-corpus comparison.
- Quality strategy: two-step review (automated proposal plus human approval before publish).

## Success Criteria
Phase 1 is successful when:
1. All seven required documents exist and use consistent terms, states, and field names.
2. Data dictionary includes required fields, types, constraints, and relationships for all seven record types.
3. Ontology defines controlled dimensions and mapping rules for cross-culture comparison.
4. Workflow pseudocode covers acquisition, extraction, normalization, tagging, linking, flagging, review, and audit.
5. Validation plan includes at least eight executable-style scenarios and clear acceptance gates.
6. Corpus strategy includes global balancing rubric and pilot list template for 50-100 texts.

## Risks and Mitigations
- Risk: false equivalence between traditions.
  - Mitigation: require evidence links, confidence scores, and reviewer notes for each commonality claim.
- Risk: inherited bias from hostile historical sources.
  - Mitigation: model source-bias flags and force explicit rationale plus linked evidence.
- Risk: ambiguous translation effects.
  - Mitigation: retain original-language passage, normalized-language passage, and translation-confidence fields.

## Decision Record (Locked for Phase 1)
1. Milestone type: research brief package.
2. Audience: researchers plus public.
3. Pilot size: 50-100 texts.
4. Coverage model: globally balanced set.
5. Similarity model: ritual-pattern ontology.
6. Flag focus: uncertainty and source bias.
7. Review model: automated proposal plus human approval.
