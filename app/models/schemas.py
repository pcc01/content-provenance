"""
Data models for the AI Translation Provenance System.
Implements W3C PROV-DM concepts: Entity, Activity, Agent, and their relations.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
import uuid


# ─── Enumerations ─────────────────────────────────────────────────────────────

class TranslationMethod(str, Enum):
    AI = "ai"
    HUMAN = "human"
    HYBRID = "hybrid"          # AI draft + human post-edit


class DeploymentContext(str, Enum):
    WEBSITE = "website"
    BANNER_AD = "banner_ad"
    MARKETING_CAMPAIGN = "marketing_campaign"
    EMAIL = "email"
    MOBILE_APP = "mobile_app"
    SOCIAL_MEDIA = "social_media"
    PRINT = "print"
    API = "api"
    OTHER = "other"


class TranslationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ProvenanceRelation(str, Enum):
    WAS_GENERATED_BY = "wasGeneratedBy"      # W3C PROV
    WAS_DERIVED_FROM = "wasDerivedFrom"      # W3C PROV
    WAS_ATTRIBUTED_TO = "wasAttributedTo"    # W3C PROV
    USED = "used"                            # W3C PROV
    WAS_ASSOCIATED_WITH = "wasAssociatedWith"# W3C PROV
    WAS_INFORMED_BY = "wasInformedBy"        # W3C PROV
    WAS_REVISION_OF = "wasRevisionOf"        # W3C PROV — links successive versions of a translation


class IngestDirection(str, Enum):
    IN = "in"
    OUT = "out"


class RedriveRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RedriveOutcome(str, Enum):
    REDRIVEN = "redriven"
    SKIPPED_ABOVE_THRESHOLD = "skipped_above_threshold"
    FAILED = "failed"
    NO_BUDGET = "no_budget"
    PENDING_APPROVAL = "pending_approval"  # human-in-the-loop: redriven text proposed, not yet applied
    REJECTED = "rejected"                  # a human reviewer declined the proposed redrive


class SiteAuditStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SiteAuditCheck(str, Enum):
    """The pluggable checks a SiteAudit run can enable — see
    app/core/audit/checks/. New checks just need a new value here plus a
    matching module; SiteAuditFinding.detail's free-form JSON means no
    schema change is needed for new finding shapes within a check."""
    MIXED_LOCALE = "mixed_locale"
    RTL_READINESS = "rtl_readiness"
    ICU_I18N = "icu_i18n"
    PRIVACY = "privacy"
    TEXT_EXPANSION = "text_expansion"
    FONT_COVERAGE = "font_coverage"
    HREFLANG = "hreflang"
    COOKIE_CONSENT = "cookie_consent"
    PLACEHOLDER_LEAK = "placeholder_leak"
    LOCALE_FORMAT = "locale_format"


class SiteAuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ImageAssetKind(str, Enum):
    CONTEXT = "context"            # a reference screenshot shown alongside a text segment for reviewer context
    TRANSLATABLE = "translatable"  # a source or target image asset with its own provenance chain (e.g. a banner)


class DocumentFormat(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"


# ─── W3C PROV-DM Core Concepts ───────────────────────────────────────────────

class ProvenanceAgent(BaseModel):
    """W3C PROV Agent - a person, software agent, or organization."""
    id: str = Field(default_factory=lambda: f"agent:{uuid.uuid4()}")
    name: str
    agent_type: str  # "SoftwareAgent" | "Person" | "Organization"
    model_version: Optional[str] = None          # e.g. "claude-3-7-sonnet"
    organization: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProvenanceActivity(BaseModel):
    """W3C PROV Activity - something that occurred over a period of time."""
    id: str = Field(default_factory=lambda: f"activity:{uuid.uuid4()}")
    activity_type: str                           # "Translation" | "Review" | "Publication"
    started_at: datetime
    ended_at: Optional[datetime] = None
    agent_id: str                                # who/what performed the activity
    used_entity_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProvenanceEntity(BaseModel):
    """W3C PROV Entity - a physical, digital, conceptual, or other kind of thing."""
    id: str = Field(default_factory=lambda: f"entity:{uuid.uuid4()}")
    entity_type: str                             # "SourceText" | "Translation" | "DeployedContent"
    was_generated_by: Optional[str] = None       # activity ID
    was_derived_from: Optional[str] = None       # parent entity ID
    was_attributed_to: Optional[str] = None      # agent ID
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    invalidated_at: Optional[datetime] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


# ─── Translation Models ───────────────────────────────────────────────────────

class SourceContent(BaseModel):
    """The original content to be translated."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    language: str                                # BCP-47 language tag e.g. "en-US"
    content_type: str = "text/plain"             # MIME type
    domain: Optional[str] = None                 # subject domain e.g. "legal", "marketing"
    author: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranslationUnit(BaseModel):
    """
    XLIFF-aligned translation unit.
    Maps to <unit> in XLIFF 2.0.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    source_text: str
    source_language: str
    target_text: Optional[str] = None
    target_language: str
    
    # Provenance
    translation_method: TranslationMethod
    translated_by_agent_id: str
    translated_at: Optional[datetime] = None
    reviewed_by_agent_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    
    # Quality
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    quality_score: Optional[float] = Field(None, ge=0.0, le=100.0)  # MQM scale
    
    status: TranslationStatus = TranslationStatus.PENDING
    
    # W3C PROV entity ID for this unit
    prov_entity_id: Optional[str] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranslationUnitVersion(BaseModel):
    """Full edit history for a TranslationUnit's target_text — one row per
    version. source_event distinguishes how the version came to be, which
    matters for provenance (an "import" or "redrive" version is attributed
    differently than a plain "human_edit")."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    unit_id: str
    version_number: int
    target_text: str
    translated_by_agent_id: str
    method: TranslationMethod
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_event: str = "initial"  # initial | human_edit | import | redrive
    quality_score: Optional[float] = None
    note: Optional[str] = None


class ScoreError(BaseModel):
    severity: str  # critical | major | minor
    count: int = 1


class QualityScore(BaseModel):
    """One quality assessment of a unit's CURRENT version (see
    TranslationUnitVersion). score is 0-100, lower = worse — the same
    convention peripateticware's QE scorer uses. score=None means the
    evaluator couldn't render a verdict (needs_review=True)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    unit_id: str
    version_id: Optional[str] = None
    score: Optional[float] = Field(None, ge=0.0, le=100.0)
    scorer: str  # "deterministic" | "claude" | "ollama"
    reasons: List[str] = Field(default_factory=list)
    errors: List[ScoreError] = Field(default_factory=list)
    raw_response: Optional[str] = None
    needs_review: bool = False
    scored_at: datetime = Field(default_factory=datetime.utcnow)


class RedriveRunItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    unit_id: str
    before_score: Optional[float] = None
    after_score: Optional[float] = None
    outcome: RedriveOutcome
    detail: Optional[str] = None
    # Human-in-the-loop (only populated when the run's require_human_approval
    # is set and this item's outcome is/was PENDING_APPROVAL): the candidate
    # text a human must approve before it becomes the unit's live translation.
    proposed_text: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class RedriveRun(BaseModel):
    """A single threshold-quality redrive pass: score everything in scope
    (skipping units already scored against their current version), redrive
    whatever scores below `threshold`.

    require_human_approval: when True, a below-threshold unit's redrive is
    generated but NOT applied — the item sits as PENDING_APPROVAL with its
    proposed_text until a human calls the approve/reject endpoint. Some
    organizations require a human in the loop before AI-driven changes go
    live even when the automated score/threshold decision itself is trusted;
    this makes that an opt-in step rather than the only mode."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: RedriveRunStatus = RedriveRunStatus.PENDING
    threshold: float
    scope: Dict[str, Any] = Field(default_factory=dict)  # e.g. {"target_language": "fr-FR"} or {"unit_ids": [...]}
    scoring_provider: str
    redrive_provider: str
    require_human_approval: bool = False
    triggered_by: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    items: List[RedriveRunItem] = Field(default_factory=list)


class ReviewNote(BaseModel):
    """A reviewer comment — either on one translation unit (the notes
    thread in the review UI's segment drawer) or, for Phase 10's live
    review workflow, on a whole page (`page_url`+`target_language`) for
    observations that don't map to a single segment ("use formal register
    throughout this page"). Exactly one of `unit_id` or
    (`page_url`+`target_language`) is set, never both — same polymorphic-id
    pattern already used for `provenance_bundles.translation_unit_id`.
    parent_id makes a flat list threadable without a recursive tree
    structure."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    unit_id: Optional[str] = None
    page_url: Optional[str] = None
    target_language: Optional[str] = None
    author: str
    body: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False
    parent_id: Optional[str] = None


class IngestEvent(BaseModel):
    """One row per XLIFF document entering (import) or leaving (export) the
    system — the literal 'track everything entering and leaving' ledger."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    direction: IngestDirection
    format: str = "xliff"
    source_system: Optional[str] = None
    xliff_document_id: Optional[str] = None
    unit_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DeploymentRecord(BaseModel):
    """Tracks where translated content is deployed/used."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    translation_unit_id: str
    context: DeploymentContext
    location: str                               # URL, campaign name, ad ID, etc.
    deployed_at: datetime = Field(default_factory=datetime.utcnow)
    deployed_by: Optional[str] = None
    version: Optional[str] = None
    is_active: bool = True
    retired_at: Optional[datetime] = None
    prov_entity_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranslationProject(BaseModel):
    """Groups related translations into a project."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    source_language: str
    target_languages: List[str]
    context: DeploymentContext
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    translation_units: List[str] = Field(default_factory=list)  # IDs
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Image Assets ──────────────────────────────────────────────────────────

class ImageAsset(BaseModel):
    """An uploaded image file — either a `context` screenshot shown next to
    a text segment for reviewer context, or a `translatable` image (source
    or target) that carries its own provenance chain (e.g. a localized
    banner)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: ImageAssetKind
    storage_path: str            # relative path under settings.image_storage_dir
    content_type: str
    checksum: str                # sha256 of the file contents
    original_filename: Optional[str] = None
    alt_text: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    uploaded_by: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ImageTranslationUnit(BaseModel):
    """The image-asset analogue of TranslationUnit — 'this source image,
    localized into this target language.' target_image_id is None until a
    localized image is attached (a human/tool upload, or a future
    image-generation backend). overlay_text_unit_ids optionally links to
    ordinary TranslationUnits for text embedded IN the image (e.g. a
    banner's headline), so that text gets the full text-provenance/scoring/
    redrive treatment while still being understood as part of this image."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_image_id: str
    target_image_id: Optional[str] = None
    source_language: str
    target_language: str

    translation_method: TranslationMethod
    translated_by_agent_id: str
    translated_at: Optional[datetime] = None
    reviewed_by_agent_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    quality_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    status: TranslationStatus = TranslationStatus.PENDING

    overlay_text_unit_ids: List[str] = Field(default_factory=list)
    prov_entity_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ImageContextLink(BaseModel):
    """Attaches a `context`-kind ImageAsset to a TranslationUnit — 'this
    screenshot shows this text segment in context,' for the review UI."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    image_id: str
    translation_unit_id: str
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Documents (Phase 7a: plain text / Markdown in-context review) ─────────

class Document(BaseModel):
    """A plain-text or Markdown file imported for in-context review. Its
    content lives as ordinary TranslationUnits (one per paragraph/block),
    each tagged in `metadata` with {"document_id": ..., "position": N} —
    reusing TranslationUnit's existing free-form metadata field rather than
    a join table, since ordering is the only extra structure a document
    needs. The Review Shell's DocumentViewer page fetches those units back
    in order and renders them as the "target page" the overlay SDK tags,
    the same way any other in-context-reviewed page works."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    original_filename: Optional[str] = None
    format: DocumentFormat
    source_language: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    uploaded_by: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Page Snapshots (Phase 8: non-cooperative page review) ─────────────────

class PageSnapshot(BaseModel):
    """A fetched-and-rewritten copy of an arbitrary URL — the "template" for
    Phase 8's fetch+rewrite loader, and the structural anchor Phase 9's
    time-travel reconstruction reads from. `html` is the fully rewritten
    document (data-tu-id tags, target-locale text baked in at fetch time,
    absolute asset URLs, the review-sdk script injected) — re-fetching
    creates a NEW row rather than overwriting, so the history of what a
    page's structure looked like over time is preserved the same way
    TranslationUnitVersion preserves segment-level history."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    target_language: str
    html: str
    harvested_unit_ids: List[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class SiteAudit(BaseModel):
    """Phase 11 — a crawl of a THIRD-PARTY site (not this system's own
    translation units) looking for i18n/l10n/compliance issues: mixed
    locales, RTL/logical-CSS readiness, ICU/i18n-tooling usage, and privacy-
    policy language mismatches. Mirrors RedriveRun's parent-run shape, one
    level deeper (SiteAuditPage) for the crawled-page inventory."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    root_url: str
    primary_language: str
    max_pages: int = 40
    checks: List[SiteAuditCheck] = Field(default_factory=lambda: list(SiteAuditCheck))
    status: SiteAuditStatus = SiteAuditStatus.PENDING
    # The requester's email — required at the API layer (see AuditRunRequest
    # in app/api/audit.py) once this tool is public-facing: every report is
    # a lead. Optional here (not at the API boundary) so existing/internal
    # rows and any future non-lead-gen caller aren't forced to have one.
    requester_email: Optional[str] = None
    triggered_by: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    pages_crawled: int = 0
    error: Optional[str] = None


class SiteAuditPage(BaseModel):
    """One crawled page within a SiteAudit run."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str
    url: str
    html_lang_attr: Optional[str] = None
    expected_locale: Optional[str] = None
    detected_language: Optional[str] = None
    status_code: Optional[int] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class SiteAuditFinding(BaseModel):
    """One issue surfaced by a check. `finding_type` and `detail` are
    deliberately free-form (a string + a JSON blob) rather than one column
    per possible shape — new finding types across all four checks need no
    schema change, same flexibility RedriveRunItem.detail/
    ProvenanceEntity.attributes already rely on elsewhere. `page_id` is
    nullable because some findings span two pages (e.g. a privacy policy's
    language not matching the page that links to it) — the secondary URL
    lives in `detail`, not a second FK column."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str
    page_id: Optional[str] = None
    check: SiteAuditCheck
    finding_type: str
    severity: SiteAuditSeverity = SiteAuditSeverity.WARNING
    summary: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Full Provenance Record ───────────────────────────────────────────────────

class ProvenanceRecord(BaseModel):
    """
    Complete W3C PROV-DM provenance bundle for a translation unit.
    Serializable to PROV-N, PROV-JSON, or PROV-XML.
    Cross-references the XLIFF 2.0 document that embeds this provenance.
    """
    bundle_id: str = Field(default_factory=lambda: f"bundle:{uuid.uuid4()}")
    translation_unit_id: str
    # Cross-reference: the XLIFF document that carries embedded provenance
    xliff_document_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # W3C PROV core elements
    entities: List[ProvenanceEntity] = Field(default_factory=list)
    activities: List[ProvenanceActivity] = Field(default_factory=list)
    agents: List[ProvenanceAgent] = Field(default_factory=list)
    
    # Relations (W3C PROV)
    relations: List[Dict[str, str]] = Field(default_factory=list)
    
    # Human-readable summary
    summary: Optional[str] = None


# ─── API Request/Response Schemas ─────────────────────────────────────────────

class TranslateRequest(BaseModel):
    source_text: str = Field(..., min_length=1, max_length=50000)
    source_language: str = Field(..., example="en-US")
    target_language: str = Field(..., example="fr-FR")
    method: TranslationMethod = TranslationMethod.AI
    context: DeploymentContext = DeploymentContext.WEBSITE
    deployment_location: Optional[str] = Field(None, example="https://example.com/about")
    project_id: Optional[str] = None
    domain: Optional[str] = Field(None, example="marketing")
    translator_name: Optional[str] = None       # for human translations


class TranslateResponse(BaseModel):
    translation_unit_id: str
    source_text: str
    translated_text: str
    source_language: str
    target_language: str
    method: TranslationMethod
    confidence_score: Optional[float]
    provenance_record_id: str
    xliff_document_id: str
    status: TranslationStatus
    translated_at: datetime


class ProvenanceQueryResponse(BaseModel):
    translation_unit_id: str
    provenance: ProvenanceRecord
    deployment_records: List[DeploymentRecord]
    xliff_reference: str
    prov_json: Dict[str, Any]


class SearchRequest(BaseModel):
    query: str
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    method: Optional[TranslationMethod] = None
    context: Optional[DeploymentContext] = None
    top_k: int = Field(10, ge=1, le=50)
