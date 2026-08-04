import type { TranslationUnitVersion } from "../api/client";
import { QualityBadge } from "./QualityBadge";

const EVENT_LABEL: Record<string, string> = {
  initial: "Initial translation",
  human_edit: "Human edit",
  import: "Imported",
  redrive: "Redriven",
};

export function VersionHistory({ versions }: { versions: TranslationUnitVersion[] }) {
  if (versions.length === 0) return <p style={{ color: "#6b7280" }}>No version history yet.</p>;

  return (
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
        </li>
      ))}
    </ol>
  );
}
