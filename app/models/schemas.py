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
