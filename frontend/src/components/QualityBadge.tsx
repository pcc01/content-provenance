function color(score: number | null): string {
  if (score === null) return "#8a8a8a";
  if (score < 50) return "#e5484d";
  if (score < 80) return "#f5a524";
  return "#30a46c";
}

export function QualityBadge({ score }: { score: number | null }) {
  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "2px 10px", borderRadius: 999, fontSize: 13, fontWeight: 600,
        color: "white", background: color(score),
      }}
    >
      {score === null ? "Unscored" : Math.round(score)}
    </span>
  );
}
