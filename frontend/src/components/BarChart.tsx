// Phase 18 — hand-rolled, dependency-free bar chart (matches this
// codebase's existing "no heavy dependency for a simple thing" convention
// — same reasoning app/core/llm_clients.py already applies to raw httpx
// over provider SDKs). Horizontal bars read better than vertical ones for
// short text labels (method/status names) at this width.
interface BarChartProps {
  data: { label: string; value: number; color?: string }[];
  defaultColor?: string;
}

export function BarChart({ data, defaultColor = "#111827" }: BarChartProps) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {data.map((d) => (
        <div key={d.label} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 90, fontSize: 12, color: "#6b7280", textAlign: "right", flexShrink: 0 }}>
            {d.label}
          </div>
          <div style={{ flex: 1, background: "#f3f4f6", borderRadius: 5, height: 20, overflow: "hidden" }}>
            <div
              style={{
                width: `${(d.value / max) * 100}%`, background: d.color ?? defaultColor, height: "100%",
                borderRadius: 5, transition: "width 0.3s ease",
              }}
            />
          </div>
          <div style={{ width: 44, fontSize: 12, fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
            {d.value.toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  );
}
