function color(score: number | null): string {
  if (score === null) return "#8a8a8a";
  if (score < 50) return "#e5484d";
  if (score < 80) return "#f5a524";
  return "#30a46c";
}

// hardFail (Phase 15) — MQM's "any critical error ⇒ automatic Fail" rule:
// a unit can score 75/100 (reads "mostly fine") and still be hard_fail=true
// because of one critical error. Optional/additive so existing call sites
// that don't have QualityScore.hard_fail in scope (only RedriveRunItem's
// before/after numbers) keep working unchanged.
export function QualityBadge({ score, hardFail }: { score: number | null; hardFail?: boolean }) {
  return (
    <span
      title={hardFail ? "Hard fail: contains a critical error" : undefined}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "2px 10px", borderRadius: 999, fontSize: 13, fontWeight: 600,
        color: "white", background: hardFail ? "#e5484d" : color(score),
        border: hardFail ? "2px solid #7f1d1d" : "none",
      }}
    >
      {hardFail && "⚠ "}{score === null ? "Unscored" : Math.round(score)}
    </span>
  );
}
