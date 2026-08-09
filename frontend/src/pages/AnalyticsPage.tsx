import { useEffect, useState } from "react";
import { api, type Stats } from "../api/client";
import { BarChart } from "../components/BarChart";
import { DonutChart } from "../components/DonutChart";
import { PageIntro } from "../components/PageIntro";

// Phase 18 — was "Dashboard," nested inside Quality Review's tab bar.
// Renamed and promoted to its own top-level segment: the numbers here
// (total translations, deployments, agents, projects, and the method/
// status breakdowns) aggregate across Content Creation, Quality Review,
// AND Audit — it was never really a Quality Review sub-page, just parked
// there because that segment happened to exist first.
const STATUS_COLORS: Record<string, string> = {
  pending: "#9ca3af",
  in_progress: "#3b82f6",
  completed: "#30a46c",
  reviewed: "#0ea5e9",
  published: "#111827",
  deprecated: "#e5484d",
};

const METHOD_COLORS: Record<string, string> = {
  ai: "#111827",
  human: "#30a46c",
  hybrid: "#f5a524",
};

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ padding: 16, background: "#f9fafb", borderRadius: 8 }}>
      <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{value.toLocaleString()}</div>
      <div style={{ fontSize: 12, color: "#6b7280" }}>{label}</div>
    </div>
  );
}

export function AnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => { api.getStats().then(setStats); }, []);

  return (
    <div style={{ padding: 24, maxWidth: 820 }}>
      <PageIntro title="Analytics">
        System-wide totals and breakdowns — translations, deployments, agents, and projects across
        every segment (Content Creation, Quality Review, Audit). No input required; this loads
        automatically and reflects live data.
      </PageIntro>

      {!stats ? (
        <div style={{ color: "#6b7280" }}>Loading…</div>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 32 }}>
            <Stat label="Total translations" value={stats.total_translations} />
            <Stat label="Deployments" value={stats.total_deployments} />
            <Stat label="Projects" value={stats.total_projects} />
            <Stat label="Agents" value={stats.total_agents} />
          </div>

          <div style={{ display: "flex", gap: 40, flexWrap: "wrap" }}>
            <div style={{ minWidth: 260 }}>
              <h3 style={{ fontSize: 14, marginBottom: 12 }}>By method</h3>
              <BarChart
                data={Object.entries(stats.by_method).map(([label, value]) => ({
                  label, value, color: METHOD_COLORS[label],
                }))}
              />
            </div>

            <div>
              <h3 style={{ fontSize: 14, marginBottom: 12 }}>By status</h3>
              <DonutChart
                data={Object.entries(stats.by_status).map(([label, value]) => ({
                  label, value, color: STATUS_COLORS[label] ?? "#9ca3af",
                }))}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
