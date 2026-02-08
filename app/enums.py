from enum import Enum


class RecordStatus(str, Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    published = "published"


class RightsStatus(str, Enum):
    public_domain = "public_domain"
    licensed = "licensed"
    restricted = "restricted"


class DateConfidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class ReviewerState(str, Enum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    needs_revision = "needs_revision"


class PublishState(str, Enum):
    blocked = "blocked"
    eligible = "eligible"
    published = "published"


class ReviewDecisionEnum(str, Enum):
    approve = "approve"
    reject = "reject"
    needs_revision = "needs_revision"


class SourceObjectType(str, Enum):
    text = "text"
    source = "source"
    passage = "passage"
    tag = "tag"
    link = "link"
    flag = "flag"


class ReviewableObjectType(str, Enum):
    passage = "passage"
    tag = "tag"
    link = "link"
    flag = "flag"
    text = "text"
    source = "source"


class RelationType(str, Enum):
    is_version_of = "isVersionOf"
    is_related_to = "isRelatedTo"
    shares_pattern_with = "sharesPatternWith"
    is_derived_from = "isDerivativeOf"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    dead_letter = "dead_letter"


class TranslationStatus(str, Enum):
    translated = "translated"
    needs_reprocess = "needs_reprocess"
    unresolved = "unresolved"


class ReprocessTriggerMode(str, Enum):
    manual = "manual"
    auto_threshold = "auto_threshold"
