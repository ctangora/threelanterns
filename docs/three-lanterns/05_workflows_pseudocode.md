# Three Lanterns Workflow Pseudocode (Phase 1 Spec)

## Purpose
Define implementation-ready process logic without selecting technology stack.

## Global Workflow States
- `queued`
- `in_progress`
- `blocked`
- `ready_for_review`
- `approved`
- `rejected`
- `published`

## 1) Acquisition and Rights Triage

```text
WORKFLOW AcquisitionAndRightsTriage(candidate):
  REQUIRE candidate.candidate_id
  REQUIRE candidate.source_reference

  rights_result = EvaluateLegalBasis(candidate)
  provenance_result = EvaluateProvenance(candidate)

  IF rights_result.status == "invalid":
    EmitError("rights_invalid", candidate.candidate_id)
    SetState(candidate, "blocked")
    RETURN

  IF provenance_result.status == "insufficient":
    EmitFlag(candidate, "provenance_gap", "medium", provenance_result.note)
    SetState(candidate, "blocked")
    RETURN

  SetState(candidate, "in_progress")
  Route(candidate, "SourceDocumentation")
```

## 2) Source Documentation and Identifier Assignment

```text
WORKFLOW SourceDocumentation(candidate):
  source = BuildSourceMaterialRecord(candidate)
  source.source_id = GenerateStableId("src")
  source.text_id = ResolveOrCreateTextRecord(candidate)

  VALIDATE source REQUIRED_FIELDS
  VALIDATE source.text_id EXISTS

  IF validation.failed:
    EmitError("source_validation_failed", source.source_id, validation.details)
    SetState(source, "blocked")
    RETURN

  Persist(source)
  SetState(source, "ready_for_review")
  Route(source, "DigitizationIntake")
```

## 3) Digitization/OCR/Transcription Intake

```text
WORKFLOW DigitizationIntake(source):
  intake = InitializeDigitalIntake(source.source_id)

  intake.capture_method = DetermineCaptureMethod(source.edition_witness_type)
  intake.technical_metadata = CaptureTechnicalMetadata()

  IF intake.capture_method IN ["scan", "image"]:
    intake.ocr_output = RunOCR(intake)
  ELSE IF intake.capture_method == "manual_transcription":
    intake.ocr_output = LoadTranscription(intake)
  ELSE:
    intake.ocr_output = LoadProvidedText(intake)

  quality = ValidateDigitalIntegrity(intake)
  IF quality.status == "failed":
    EmitError("digitization_quality_failed", source.source_id, quality.note)
    SetState(intake, "blocked")
    RETURN

  Persist(intake)
  Route(intake, "MultilingualExtraction")
```

## 4) Multilingual Passage Extraction and Normalization

```text
WORKFLOW MultilingualExtraction(intake):
  passages = ExtractCandidatePassages(intake.text_content)

  FOR EACH passage IN passages:
    evidence = NewPassageEvidence()
    evidence.passage_id = GenerateStableId("psg")
    evidence.text_id = intake.text_id
    evidence.source_id = intake.source_id
    evidence.source_span_locator = ResolveSpanLocator(passage)
    evidence.excerpt_original = passage.original_text
    evidence.original_language = DetectLanguage(passage.original_text)
    evidence.excerpt_normalized = NormalizeForComparison(
      passage.original_text,
      target_language = "comparison_canonical"
    )
    evidence.normalized_language = "comparison_canonical"
    evidence.extraction_confidence = ComputeExtractionConfidence(passage)
    evidence.reviewer_state = "proposed"
    evidence.publish_state = "blocked"

    VALIDATE evidence REQUIRED_FIELDS
    VALIDATE evidence.source_span_locator RESOLVES
    VALIDATE evidence.extraction_confidence IN [0.00, 1.00]

    IF validation.failed:
      EmitError("passage_validation_failed", evidence.passage_id, validation.details)
      CONTINUE

    Persist(evidence)

  Route(intake, "OntologyTagging")
```

## 5) Ontology Tagging with Controlled Vocabulary

```text
WORKFLOW OntologyTagging(context):
  evidence_set = FetchEvidenceByContext(context)

  FOR EACH evidence IN evidence_set:
    proposals = ProposeOntologyTerms(
      evidence.excerpt_original,
      evidence.excerpt_normalized,
      ontology_dimensions = RitualOntologyV0
    )

    FOR EACH proposal IN proposals:
      tag = NewRitualPatternTag()
      tag.tag_id = GenerateStableId("tag")
      tag.ontology_dimension = proposal.dimension
      tag.controlled_term = proposal.term
      tag.confidence = proposal.confidence
      tag.evidence_ids = [evidence.passage_id]
      tag.proposer_type = "automated"
      tag.reviewer_state = "proposed"

      IF NOT IsAllowedVocabulary(tag.ontology_dimension, tag.controlled_term):
        QueuePendingVocabTerm(tag)
        EmitError("controlled_term_not_allowed", tag.tag_id)
        CONTINUE

      Persist(tag)

  Route(context, "CommonalityProposal")
```

## 6) Cross-Cultural Commonality Proposal

```text
WORKFLOW CommonalityProposal(context):
  candidate_pairs = BuildComparisonPairs(
    scope = "cross_cultural",
    unit = "passage_level"
  )

  FOR EACH pair IN candidate_pairs:
    dimension_scores = ComputeDimensionOverlap(pair, weights = OntologyWeightsV0)
    similarity = WeightedSum(dimension_scores)

    IF similarity < 0.35:
      CONTINUE

    link = NewCommonalityLink()
    link.link_id = GenerateStableId("lnk")
    link.source_entity_type = pair.source_type
    link.source_entity_id = pair.source_id
    link.target_entity_type = pair.target_type
    link.target_entity_id = pair.target_id
    link.relation_type = "sharesPatternWith"
    link.weighted_similarity_score = similarity
    link.evidence_ids = pair.supporting_passage_ids
    link.reviewer_decision = "proposed"

    VALIDATE link.evidence_ids COUNT >= 1
    VALIDATE link.weighted_similarity_score IN [0.00, 1.00]

    Persist(link)

  Route(context, "Flagging")
```

## 7) Uncertainty and Source-Bias Flagging

```text
WORKFLOW Flagging(context):
  objects = FetchObjectsForFlagging(context)

  FOR EACH object IN objects:
    rules = EvaluateUncertaintyAndBiasRules(object)

    FOR EACH rule_hit IN rules:
      flag = NewFlagRecord()
      flag.flag_id = GenerateStableId("flg")
      flag.object_type = object.type
      flag.object_id = object.id
      flag.flag_type = rule_hit.flag_type
      flag.severity = rule_hit.severity
      flag.rationale = rule_hit.rationale
      flag.evidence_ids = rule_hit.evidence_ids
      flag.reviewer_state = "proposed"

      VALIDATE flag.rationale NON_EMPTY
      VALIDATE flag.evidence_ids COUNT >= 1

      Persist(flag)

  Route(context, "HumanReview")
```

## 8) Human Review, Decision Logging, and Audit

```text
WORKFLOW HumanReview(context):
  review_queue = FetchReviewQueue(context)

  FOR EACH item IN review_queue:
    decision = ReviewerDecision(item)

    review = NewReviewDecision()
    review.review_id = GenerateStableId("rev")
    review.object_type = item.type
    review.object_id = item.id
    review.reviewer_id = decision.reviewer_id
    review.decision = decision.outcome
    review.decision_timestamp = CurrentUTC()
    review.notes = decision.notes
    review.previous_state = item.reviewer_state
    review.new_state = MapDecisionToState(decision.outcome)

    Persist(review)
    UpdateObjectReviewState(item, review.new_state)

    IF review.decision == "approve":
      MarkEligibleForPublish(item)
    ELSE:
      KeepBlocked(item)

    EmitAuditEvent(
      actor = review.reviewer_id,
      action = "review_decision",
      object = item.id,
      timestamp = review.decision_timestamp
    )
```

## 9) Publish-Ready Record Assembly

```text
WORKFLOW PublishAssembly(context):
  candidates = FetchPublishCandidates(context)

  FOR EACH candidate IN candidates:
    IF NOT HasApprovedReview(candidate):
      CONTINUE
    IF HasBlockingValidationErrors(candidate):
      CONTINUE
    IF MissingRequiredDependencies(candidate):
      CONTINUE

    package = BuildPublishPackage(candidate)
    package.includes = [
      canonical_record,
      linked_source_material,
      approved_passage_evidence,
      approved_tags,
      approved_commonality_links,
      approved_flags,
      review_history_summary
    ]

    Persist(package)
    SetState(candidate, "published")

    EmitAuditEvent(
      actor = "system",
      action = "publish",
      object = candidate.id,
      timestamp = CurrentUTC()
    )
```

## Error Handling and Recovery

```text
WORKFLOW ErrorHandling(error_event):
  LogError(error_event.code, error_event.object_id, error_event.details)

  IF error_event.severity == "critical":
    HaltPipeline(error_event.pipeline_id)
    OpenManualResolutionTask(error_event)
  ELSE:
    ContinuePipeline(error_event.pipeline_id)
    QueueCorrectionTask(error_event)
```

## Audit Trail Requirements
Every state transition and decision must emit:
- actor
- action
- object_type
- object_id
- previous_state
- new_state
- timestamp
- correlation_id

Retention requirement for audit events:
- Keep full audit trail for all reviewable objects through all lifecycle states.
