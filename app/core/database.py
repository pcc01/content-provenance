"""
Database layer - uses an in-memory store for demo purposes.
In production, replace with PostgreSQL + pgvector or similar.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from app.models.schemas import (
    TranslationUnit, ProvenanceRecord, DeploymentRecord,
    TranslationProject, ProvenanceAgent, ProvenanceActivity, ProvenanceEntity,
    TranslationMethod, TranslationStatus
)


class InMemoryDatabase:
    """Thread-safe in-memory store simulating a real database."""
    
    def __init__(self):
        self.translation_units: Dict[str, TranslationUnit] = {}
        self.provenance_records: Dict[str, ProvenanceRecord] = {}
        self.deployment_records: Dict[str, DeploymentRecord] = {}
        self.projects: Dict[str, TranslationProject] = {}
        self.agents: Dict[str, ProvenanceAgent] = {}
        self.xliff_documents: Dict[str, str] = {}          # id -> XML string
        self.prov_json_docs: Dict[str, Dict] = {}          # bundle_id -> PROV-JSON

    # ── Translation Units ─────────────────────────────────────────────────────
    
    def save_translation_unit(self, unit: TranslationUnit) -> TranslationUnit:
        self.translation_units[unit.id] = unit
        return unit

    def get_translation_unit(self, unit_id: str) -> Optional[TranslationUnit]:
        return self.translation_units.get(unit_id)

    def list_translation_units(
        self,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        method: Optional[TranslationMethod] = None,
        status: Optional[TranslationStatus] = None,
        limit: int = 50
    ) -> List[TranslationUnit]:
        units = list(self.translation_units.values())
        if source_language:
            units = [u for u in units if u.source_language == source_language]
        if target_language:
            units = [u for u in units if u.target_language == target_language]
        if method:
            units = [u for u in units if u.translation_method == method]
        if status:
            units = [u for u in units if u.status == status]
        return units[:limit]

    # ── Provenance Records ────────────────────────────────────────────────────

    def save_provenance_record(self, record: ProvenanceRecord) -> ProvenanceRecord:
        self.provenance_records[record.bundle_id] = record
        # Also index by translation_unit_id
        self.provenance_records[f"tu:{record.translation_unit_id}"] = record
        return record

    def get_provenance_by_unit(self, unit_id: str) -> Optional[ProvenanceRecord]:
        return self.provenance_records.get(f"tu:{unit_id}")

    def get_provenance_by_bundle(self, bundle_id: str) -> Optional[ProvenanceRecord]:
        return self.provenance_records.get(bundle_id)

    # ── Deployment Records ────────────────────────────────────────────────────

    def save_deployment_record(self, record: DeploymentRecord) -> DeploymentRecord:
        self.deployment_records[record.id] = record
        return record

    def get_deployments_for_unit(self, unit_id: str) -> List[DeploymentRecord]:
        return [
            r for r in self.deployment_records.values()
            if r.translation_unit_id == unit_id
        ]

    # ── Projects ──────────────────────────────────────────────────────────────

    def save_project(self, project: TranslationProject) -> TranslationProject:
        self.projects[project.id] = project
        return project

    def get_project(self, project_id: str) -> Optional[TranslationProject]:
        return self.projects.get(project_id)

    # ── Agents ───────────────────────────────────────────────────────────────

    def save_agent(self, agent: ProvenanceAgent) -> ProvenanceAgent:
        self.agents[agent.id] = agent
        return agent

    def get_or_create_agent(self, name: str, agent_type: str, **kwargs) -> ProvenanceAgent:
        # Look for existing agent
        for agent in self.agents.values():
            if agent.name == name and agent.agent_type == agent_type:
                return agent
        # Create new
        agent = ProvenanceAgent(name=name, agent_type=agent_type, **kwargs)
        return self.save_agent(agent)

    # ── XLIFF Documents ───────────────────────────────────────────────────────

    def save_xliff(self, doc_id: str, xml_content: str) -> str:
        self.xliff_documents[doc_id] = xml_content
        return doc_id

    def get_xliff(self, doc_id: str) -> Optional[str]:
        return self.xliff_documents.get(doc_id)

    # ── PROV-JSON ─────────────────────────────────────────────────────────────

    def save_prov_json(self, bundle_id: str, prov_doc: Dict) -> None:
        self.prov_json_docs[bundle_id] = prov_doc

    def get_prov_json(self, bundle_id: str) -> Optional[Dict]:
        return self.prov_json_docs.get(bundle_id)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        units = list(self.translation_units.values())
        return {
            "total_translations": len(units),
            "by_method": {
                "ai": sum(1 for u in units if u.translation_method.value == "ai"),
                "human": sum(1 for u in units if u.translation_method.value == "human"),
                "hybrid": sum(1 for u in units if u.translation_method.value == "hybrid"),
            },
            "by_status": {
                s.value: sum(1 for u in units if u.status == s)
                for s in TranslationStatus
            },
            "total_deployments": len(self.deployment_records),
            "total_projects": len(self.projects),
            "total_agents": len(self.agents),
        }


# Singleton instance
_db: Optional[InMemoryDatabase] = None


async def init_db():
    global _db
    _db = InMemoryDatabase()
    # Seed some default agents
    _db.get_or_create_agent(
        name="claude-3-7-sonnet",
        agent_type="SoftwareAgent",
        model_version="claude-3-7-sonnet-20250219",
        organization="Anthropic",
        metadata={"capabilities": ["translation", "summarization"]}
    )
    _db.get_or_create_agent(
        name="System",
        agent_type="SoftwareAgent",
        organization="AI Provenance System",
        metadata={"role": "orchestration"}
    )
    print("✓ Database initialized")


def get_db() -> InMemoryDatabase:
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db
