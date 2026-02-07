# Three Lanterns Ritual Ontology v0

## Purpose
Provide a structured pattern language for comparing rituals across cultures without collapsing differences.  
The ontology supports passage-level evidence, transparent confidence, and reviewable similarity scoring.

## Design Principles
1. Evidence-first: every ontology assignment must link to one or more `PassageEvidence` records.
2. Comparative clarity: compare dimensions, not assumptions.
3. Non-equivalence default: similarity is probabilistic and reviewable, not identity by default.
4. Traceable uncertainty: low-confidence assignments remain visible with flags and rationale.

## Dimension Model
Each tagged passage may map to one or more dimensions below.

### `ritual_intent`
What the ritual seeks to achieve.
- `healing`
- `protection`
- `purification`
- `fertility_abundance`
- `initiation_transition`
- `divination`
- `spirit_contact`
- `curse_binding`
- `atonement_repair`
- `sovereignty_legitimation`

### `ritual_actors`
Who performs or authorizes the ritual.
- `specialist_priest`
- `household_practitioner`
- `initiate_group`
- `ruler_state_actor`
- `community_collective`
- `spirit_nonhuman_agent`

### `ritual_actions`
What is done procedurally.
- `invocation`
- `chant_recitation`
- `anointing`
- `offering_deposit`
- `fire_operation`
- `water_operation`
- `gesture_sequence`
- `circumambulation`
- `inscription_writing`
- `burial_interment`

### `materials_tools`
What objects/materials are required.
- `plant_materia`
- `mineral_materia`
- `animal_materia`
- `vessel_container`
- `blade_tool`
- `cord_binding_material`
- `lamp_flame`
- `tablet_scroll`
- `powder_incense`
- `liquid_elixir`

### `time_timing`
When the ritual occurs.
- `seasonal_calendar`
- `lunar_phase`
- `solar_marker`
- `night_operation`
- `dawn_operation`
- `hourly_auspicious_window`
- `life_cycle_event`

### `location_setting`
Where the ritual occurs.
- `domestic_space`
- `temple_sanctuary`
- `open_landscape`
- `water_edge`
- `burial_site`
- `threshold_crossing`
- `restricted_chamber`

### `invocation_structure`
How sacred names, powers, or authorities are called.
- `deity_address`
- `ancestor_address`
- `angelic_hierarchy`
- `spirit_command`
- `formulaic_epithet_sequence`
- `vow_oath_clause`

### `exchange_offering`
What reciprocity or offering logic is present.
- `food_offering`
- `liquid_libation`
- `burnt_offering`
- `votive_object`
- `spoken_vow_exchange`
- `service_obligation`

### `protection_boundary`
How boundaries are established.
- `circle_boundary`
- `threshold_marking`
- `name_seal`
- `apotropaic_symbol`
- `protective_text_inscription`
- `guardianship_invocation`

### `divination_modality`
How information is sought.
- `lot_casting`
- `dream_incubation`
- `omen_reading`
- `astrological_reading`
- `scrying_surface`
- `mediumship`

### `outcome_claim`
How outcomes are described.
- `material_change`
- `status_change`
- `knowledge_revelation`
- `protection_confirmed`
- `curse_effect_claim`
- `healing_claim`
- `uncertain_or_symbolic`

## Mapping Guidance
1. Anchor each tag to the smallest meaningful passage span.
2. Prefer direct textual evidence over inferred context.
3. If multiple terms in one dimension apply, assign all with separate confidence values.
4. If term fit is unclear, assign lowest acceptable confidence and attach a `FlagRecord`.
5. Never infer relation identity from one shared dimension; require multi-dimension evidence.

## Cross-Culture Commonality Scoring
`sharesPatternWith` proposals should use weighted dimension overlap:

- `ritual_intent`: 0.18
- `ritual_actions`: 0.18
- `materials_tools`: 0.13
- `invocation_structure`: 0.13
- `time_timing`: 0.09
- `location_setting`: 0.08
- `exchange_offering`: 0.08
- `protection_boundary`: 0.06
- `divination_modality`: 0.04
- `ritual_actors`: 0.02
- `outcome_claim`: 0.01

Score interpretation:
- >= 0.75: high-confidence pattern similarity candidate.
- 0.55 to 0.74: medium-confidence candidate requiring review notes.
- 0.35 to 0.54: weak similarity, keep as exploratory only.
- < 0.35: no link proposal by default.

## Required Review Conditions
A `sharesPatternWith` proposal may move to `approved` only if:
1. At least two dimensions include medium-or-higher confidence evidence.
2. Source spans are independently verifiable.
3. At least one reviewer note explains why the match is not false equivalence.
4. Any relevant uncertainty/source-bias flags are resolved or acknowledged.

## Vocabulary Governance
- New terms enter `pending_vocab` with rationale and example passage evidence.
- Approved terms must include dimension placement and disambiguation note.
- Deprecated terms remain queryable for backward compatibility.
