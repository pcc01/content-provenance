// Phase 18 — SVG donut, same "hand-rolled, no chart library" reasoning as
// BarChart.tsx. Classic stroke-dasharray-per-segment technique: each slice
// is one full-circle <circle> stroked only along its share of the
// circumference, offset by every prior slice's share.
interface DonutChartProps {
  data: { label: string; value: number; color: string }[];
  size?: number;
}

export function DonutChart({ data, size = 140 }: DonutChartProps) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const r = 40;
  const circumference = 2 * Math.PI * r;
  let cumulative = 0;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
      <svg width={size} height={size} viewBox="0 0 100 100" style={{ transform: "rotate(-90deg)", flexShrink: 0 }}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="#f3f4f6" strokeWidth="14" />
        {total > 0 && data.map((d) => {
          const fraction = d.value / total;
          const dash = fraction * circumference;
          const offset = -cumulative;
          cumulative += dash;
          if (d.value === 0) return null;
          return (
            <circle
              key={d.label} cx="50" cy="50" r={r} fill="none" stroke={d.color} strokeWidth="14"
              strokeDasharray={`${dash} ${circumference - dash}`} strokeDashoffset={offset}
              strokeLinecap={data.filter((x) => x.value > 0).length === 1 ? "butt" : "square"}
            />
          );
        })}
        <text x="50" y="50" textAnchor="middle" dominantBaseline="central"
              style={{ transform: "rotate(90deg)", transformOrigin: "50px 50px", fontSize: 18, fontWeight: 700, fill: "#111827" }}>
          {total.toLocaleString()}
        </text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {data.map((d) => (
          <div key={d.label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: d.color, flexShrink: 0 }} />
            <span style={{ color: "#374151" }}>{d.label}</span>
            <span style={{ color: "#9ca3af", fontVariantNumeric: "tabular-nums" }}>
              {d.value.toLocaleString()}{total > 0 && ` (${Math.round((d.value / total) * 100)}%)`}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
