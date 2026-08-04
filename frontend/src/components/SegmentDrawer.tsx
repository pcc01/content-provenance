import { useEffect, useState } from "react";
import { api, type ProvenanceResponse, type TranslationUnit, type TranslationUnitVersion } from "../api/client";
import { NotesThread } from "./NotesThread";
import { ProvenancePanel } from "./ProvenancePanel";
import { QualityBadge } from "./QualityBadge";
import { VersionHistory } from "./VersionHistory";

interface Props {
  unitId: string;
  onClose: () => void;
  onPreview?: (text: string) => void; // posts tu:preview into the framed page — visual only, not persisted
}

type Tab = "details" | "history" | "provenance" | "notes";

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
    </div>
  );
}

export function SegmentDrawer({ unitId, onClose, onPreview }: Props) {
  const [unit, setUnit] = useState<TranslationUnit | null>(null);
  const [versions, setVersions] = useState<TranslationUnitVersion[]>([]);
  const [provenance, setProvenance] = useState<ProvenanceResponse["provenance"] | null>(null);
  const [tab, setTab] = useState<Tab>("details");
  const [draft, setDraft] = useState("");
  const [proposedBy, setProposedBy] = useState("reviewer@example.com");
  const [proposeStatus, setProposeStatus] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [proposeError, setProposeError] = useState<string | null>(null);

  function reload() {
    api.getTranslation(unitId).then((u) => { setUnit(u); setDraft(u.target_text ?? ""); });
    api.getVersions(unitId).then(setVersions);
    api.getProvenance(unitId).then((r) => setProvenance(r.provenance));
  }

  useEffect(() => {
    setUnit(null);
    setProvenance(null);
    setTab("details");
    setProposeStatus("idle");
    setProposeError(null);
    reload();
  }, [unitId]);

  async function handlePropose() {
    if (!unit || !draft.trim()) return;
    setProposeStatus("busy");
    setProposeError(null);
    try {
      await api.proposeTranslation(unit.id, draft, proposedBy);
      setProposeStatus("done");
    } catch (e) {
      setProposeError(e instanceof Error ? e.message : String(e));
      setProposeStatus("error");
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
        {(["details", "history", "provenance", "notes"] as Tab[]).map((t) => (
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
          </div>
        )}

        {tab === "history" && <VersionHistory unitId={unitId} versions={versions} onReverted={reload} />}
        {tab === "provenance" && provenance && <ProvenancePanel provenance={provenance} />}
        {tab === "notes" && <NotesThread unitId={unitId} />}
      </div>
    </aside>
  );
}
