import type { TranslationUnit } from "../api/client";
import { QualityBadge } from "./QualityBadge";

type Segment = TranslationUnit & { latest_score: number | null };

interface Props {
  segments: Segment[];
  selectedId: string | null;
  onSelect: (tuId: string) => void;
}

// Worst-score-first sidebar — the accessibility/discoverability fallback for
// off-screen, conditionally-rendered, or hover-only content that isn't
// visually obvious to click on the framed page itself. Keeps the worklist
// value of a segment grid without making the grid the primary interaction.
export function PageFlaggedList({ segments, selectedId, onSelect }: Props) {
  const sorted = [...segments].sort((a, b) => (a.latest_score ?? 100) - (b.latest_score ?? 100));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontSize: 12, color: "#6b7280", fontWeight: 600, marginBottom: 4 }}>
        Segments on this page ({sorted.length})
      </div>
      {sorted.length === 0 && <p style={{ fontSize: 12, color: "#9ca3af" }}>Load a page to see its segments here.</p>}
      {sorted.map((seg) => (
        <button
          key={seg.id}
          onClick={() => onSelect(seg.id)}
          style={{
            textAlign: "left", display: "flex", alignItems: "center", gap: 8,
            padding: "6px 8px", borderRadius: 6, cursor: "pointer", fontSize: 13,
            border: seg.id === selectedId ? "1px solid #111827" : "1px solid #e5e7eb",
            background: seg.id === selectedId ? "#f3f4f6" : "white",
          }}
        >
          <QualityBadge score={seg.latest_score} />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {seg.target_text || seg.source_text}
          </span>
        </button>
      ))}
    </div>
  );
}
