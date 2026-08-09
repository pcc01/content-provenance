import { useEffect, useState } from "react";
import {
  api, type DeploymentRecord, type ProvenanceResponse, type TranslationUnit, type TranslationUnitVersion,
} from "../api/client";
import { ContextImages } from "./ContextImages";
import { MetricsPanel } from "./MetricsPanel";
import { NotesThread } from "./NotesThread";
import { ProvenancePanel } from "./ProvenancePanel";
import { QualityBadge } from "./QualityBadge";
import { VersionHistory } from "./VersionHistory";

interface Props {
  unitId: string;
  onClose: () => void;
  onPreview?: (text: string) => void; // posts tu:preview into the framed page — visual only, not persisted
  onProposed?: () => void; // fires after a proposal is saved, so the page can refresh pending-state UI
}

type Tab = "details" | "history" | "provenance" | "metrics" | "notes";

const DEPLOYMENT_CONTEXTS = [
  "website", "banner_ad", "marketing_campaign", "email", "mobile_app", "social_media", "print", "api", "other",
];

function TranslatedByLine({
  unit, provenance,
}: {
  unit: TranslationUnit;
  provenance: ProvenanceResponse["provenance"] | null;
}) {
  const agent = provenance?.agents.find((a) => a.id === unit.translated_by_agent_id);

  return (
    <div style={{ fontSize: 12, color: "#6b7280", background: "#f9fafb", padding: 8, borderRadius: 6 }}>
      <div>
        <strong style={{ color: "#111827" }}>Model:</strong>{" "}
        {agent ? (
          <>
            {agent.name}
            {agent.model_version && agent.model_version !== agent.name ? ` (${agent.model_version})` : ""}
            {agent.organization ? ` · ${agent.organization}` : ""}
          </>
        ) : (
          "loading…"
        )}
      </div>
      <div>Method: {unit.translation_method}</div>
      {unit.translated_at && <div>Translated {new Date(unit.translated_at).toLocaleString()}</div>}
      {unit.reviewed_at && <div>Reviewed {new Date(unit.reviewed_at).toLocaleString()}</div>}
    </div>
  );
}

export function SegmentDrawer({ unitId, onClose, onPreview, onProposed }: Props) {
  const [unit, setUnit] = useState<TranslationUnit | null>(null);
  const [versions, setVersions] = useState<TranslationUnitVersion[]>([]);
  const [provenance, setProvenance] = useState<ProvenanceResponse["provenance"] | null>(null);
  const [deployments, setDeployments] = useState<DeploymentRecord[]>([]);
  const [tab, setTab] = useState<Tab>("details");
  const [draft, setDraft] = useState("");
  const [proposedBy, setProposedBy] = useState("reviewer@example.com");
  const [proposeStatus, setProposeStatus] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [proposeError, setProposeError] = useState<string | null>(null);

  // Phase 17 — mark-as-reviewed had no UI at all despite the backend
  // recording reviewed_by/reviewed_at (see TranslatedByLine above).
  const [reviewerName, setReviewerName] = useState("reviewer@example.com");
  const [reviewStatus, setReviewStatus] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [reviewError, setReviewError] = useState<string | null>(null);

  // Phase 17 — same story for deployment recording; history is shown
  // read-only in the Provenance tab, this is the write side.
  const [deployContext, setDeployContext] = useState("website");
  const [deployLocation, setDeployLocation] = useState("");
  const [deployBy, setDeployBy] = useState("");
  const [deployStatus, setDeployStatus] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [deployError, setDeployError] = useState<string | null>(null);

  function reload() {
    api.getTranslation(unitId).then((u) => { setUnit(u); setDraft(u.target_text ?? ""); });
    api.getVersions(unitId).then(setVersions);
    api.getProvenance(unitId).then((r) => { setProvenance(r.provenance); setDeployments(r.deployments); });
  }

  useEffect(() => {
    setUnit(null);
    setProvenance(null);
    setDeployments([]);
    setTab("details");
    setProposeStatus("idle");
    setProposeError(null);
    setReviewStatus("idle");
    setReviewError(null);
    setDeployStatus("idle");
    setDeployError(null);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitId]);

  async function handlePropose() {
    if (!unit || !draft.trim()) return;
    setProposeStatus("busy");
    setProposeError(null);
    try {
      await api.proposeTranslation(unit.id, draft, proposedBy);
      setProposeStatus("done");
      onProposed?.();
    } catch (e) {
      setProposeError(e instanceof Error ? e.message : String(e));
      setProposeStatus("error");
    }
  }

  async function handleMarkReviewed() {
    if (!unit || !reviewerName.trim()) return;
    setReviewStatus("busy");
    setReviewError(null);
    try {
      await api.markReviewed(unit.id, reviewerName.trim(), unit.quality_score ?? undefined);
      setReviewStatus("done");
      reload();
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : String(e));
      setReviewStatus("error");
    }
  }

  async function handleRecordDeployment() {
    if (!unit || !deployLocation.trim()) return;
    setDeployStatus("busy");
    setDeployError(null);
    try {
      await api.recordDeployment(unit.id, {
        context: deployContext, location: deployLocation.trim(), deployed_by: deployBy.trim() || undefined,
      });
      setDeployStatus("done");
      setDeployLocation("");
      reload();
    } catch (e) {
      setDeployError(e instanceof Error ? e.message : String(e));
      setDeployStatus("error");
    }
  }

  return (
    <aside style={{
      position: "fixed", top: 0, right: 0, bottom: 0, width: 420,
      background: "white", borderLeft: "1px solid #e5e7eb", boxShadow: "-4px 0 16px rgba(0,0,0,0.08)",
      display: "flex", flexDirection: "column", zIndex: 1000,
    }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", alignItems: "center", gap: 8 }}>
        <strong style={{ flex: 1, fontSize: 14 }}>Segment</strong>
        {unit && <QualityBadge score={unit.quality_score} />}
        <button onClick={onClose} style={{ cursor: "pointer", fontSize: 16, border: "none", background: "none" }}>✕</button>
      </div>

      <div style={{ display: "flex", borderBottom: "1px solid #e5e7eb" }}>
        {(["details", "history", "provenance", "metrics", "notes"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            flex: 1, padding: "8px 0", fontSize: 12, textTransform: "capitalize", cursor: "pointer",
            border: "none", background: tab === t ? "#f3f4f6" : "white",
            borderBottom: tab === t ? "2px solid #111827" : "2px solid transparent",
          }}>
            {t}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
        {!unit && <p style={{ color: "#6b7280" }}>Loading…</p>}

        {unit && tab === "details" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
                Source ({unit.source_language})
              </div>
              <div style={{ fontSize: 14, padding: 8, background: "#f9fafb", borderRadius: 6 }}>
                {unit.source_text}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
                Target ({unit.target_language}) · {unit.status}
              </div>
              <textarea
                value={draft}
                onChange={(e) => { setDraft(e.target.value); onPreview?.(e.target.value); }}
                rows={4}
                style={{ width: "100%", fontSize: 14, padding: 8, borderRadius: 6, border: "1px solid #e5e7eb", resize: "vertical" }}
              />
              <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 4, marginBottom: 8 }}>
                Live-previews on the page as you type — this does not save on its own. Use Redrive
                for a machine retranslation, or propose your own text below (goes through the same
                human-in-the-loop approval as a redrive).
              </p>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  value={proposedBy} onChange={(e) => setProposedBy(e.target.value)}
                  placeholder="Your name/email" style={{ width: 150, fontSize: 12, padding: 4 }}
                />
                <button
                  onClick={handlePropose}
                  disabled={proposeStatus === "busy" || !draft.trim() || draft === (unit.target_text ?? "")}
                  style={{ fontSize: 12, padding: "4px 10px", cursor: "pointer" }}
                >
                  {proposeStatus === "busy" ? "Proposing…" : "Propose translation"}
                </button>
              </div>
              {proposeStatus === "done" && (
                <p style={{ fontSize: 11, color: "#15803d", marginTop: 4 }}>
                  Proposed — awaiting approval in the Redrive Console.
                </p>
              )}
              {proposeError && <p style={{ fontSize: 11, color: "#b91c1c", marginTop: 4 }}>{proposeError}</p>}
            </div>
            <TranslatedByLine unit={unit} provenance={provenance} />

            <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 10 }}>
              <ContextImages unitId={unit.id} />
            </div>

            <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Mark as reviewed</div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  value={reviewerName} onChange={(e) => setReviewerName(e.target.value)}
                  placeholder="Your name/email" style={{ flex: 1, fontSize: 12, padding: 4 }}
                />
                <button
                  onClick={handleMarkReviewed}
                  disabled={reviewStatus === "busy" || !reviewerName.trim()}
                  style={{ fontSize: 12, padding: "4px 10px", cursor: "pointer" }}
                >
                  {reviewStatus === "busy" ? "Saving…" : "Mark reviewed"}
                </button>
              </div>
              {reviewStatus === "done" && <p style={{ fontSize: 11, color: "#15803d", marginTop: 4 }}>Marked reviewed.</p>}
              {reviewError && <p style={{ fontSize: 11, color: "#b91c1c", marginTop: 4 }}>{reviewError}</p>}
            </div>

            <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Record a deployment</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", gap: 6 }}>
                  <select value={deployContext} onChange={(e) => setDeployContext(e.target.value)} style={{ fontSize: 12, padding: 4 }}>
                    {DEPLOYMENT_CONTEXTS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <input
                    value={deployLocation} onChange={(e) => setDeployLocation(e.target.value)}
                    placeholder="URL / campaign / ad id" style={{ flex: 1, fontSize: 12, padding: 4 }}
                  />
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <input
                    value={deployBy} onChange={(e) => setDeployBy(e.target.value)}
                    placeholder="Deployed by (optional)" style={{ flex: 1, fontSize: 12, padding: 4 }}
                  />
                  <button
                    onClick={handleRecordDeployment}
                    disabled={deployStatus === "busy" || !deployLocation.trim()}
                    style={{ fontSize: 12, padding: "4px 10px", cursor: "pointer" }}
                  >
                    {deployStatus === "busy" ? "Saving…" : "Record"}
                  </button>
                </div>
              </div>
              {deployStatus === "done" && <p style={{ fontSize: 11, color: "#15803d", marginTop: 4 }}>Recorded — see the Provenance tab.</p>}
              {deployError && <p style={{ fontSize: 11, color: "#b91c1c", marginTop: 4 }}>{deployError}</p>}
            </div>
          </div>
        )}

        {tab === "history" && <VersionHistory unitId={unitId} versions={versions} onReverted={reload} />}
        {tab === "provenance" && provenance && <ProvenancePanel unitId={unitId} provenance={provenance} deployments={deployments} />}
        {tab === "metrics" && <MetricsPanel unitId={unitId} />}
        {tab === "notes" && <NotesThread unitId={unitId} />}
      </div>
    </aside>
  );
}
