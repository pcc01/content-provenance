import { useState } from "react";
import { api, type TranslationUnitVersion } from "../api/client";
import { QualityBadge } from "./QualityBadge";

const EVENT_LABEL: Record<string, string> = {
  initial: "Initial translation",
  human_edit: "Human edit",
  import: "Imported",
  redrive: "Redriven",
  revert: "Reverted",
};

interface Props {
  unitId: string;
  versions: TranslationUnitVersion[];
  onReverted: () => void;
}

export function VersionHistory({ unitId, versions, onReverted }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (versions.length === 0) return <p style={{ color: "#6b7280" }}>No version history yet.</p>;

  const latestId = versions[versions.length - 1].id;

  async function handleRevert(versionId: string) {
    setError(null);
    setBusyId(versionId);
    try {
      await api.revertVersion(unitId, versionId);
      onReverted();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      {error && (
        <div style={{ fontSize: 12, color: "#b91c1c", background: "#fef2f2", padding: 8, borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}
      <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 12 }}>
        {[...versions].reverse().map((v) => (
          <li key={v.id} style={{ borderLeft: "2px solid #e5e7eb", paddingLeft: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
              <strong>v{v.version_number}</strong>
              <span style={{ color: "#6b7280" }}>{EVENT_LABEL[v.source_event] ?? v.source_event}</span>
              {v.quality_score !== null && <QualityBadge score={v.quality_score} />}
              <span style={{ color: "#9ca3af", marginLeft: "auto" }}>
                {new Date(v.created_at).toLocaleString()}
              </span>
            </div>
            <div style={{ fontSize: 14, marginTop: 4 }}>{v.target_text}</div>
            {v.note && <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{v.note}</div>}
            {v.id !== latestId && (
              <button
                onClick={() => handleRevert(v.id)}
                disabled={busyId !== null}
                style={{ marginTop: 6, fontSize: 12, padding: "3px 10px", cursor: "pointer" }}
              >
                {busyId === v.id ? "Reverting…" : "Revert to this version"}
              </button>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
