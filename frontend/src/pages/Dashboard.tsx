import { useEffect, useState } from "react";
import { api, type Stats } from "../api/client";
import { PageIntro } from "../components/PageIntro";

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => { api.getStats().then(setStats); }, []);

  if (!stats) return <div style={{ padding: 24 }}>Loading…</div>;

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <PageIntro title="Dashboard">
        System-wide totals — translations, deployments, agents, and breakdowns by method and
        status. No input required; this loads automatically and reflects live data.
      </PageIntro>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        <Stat label="Total translations" value={stats.total_translations} />
        <Stat label="Deployments" value={stats.total_deployments} />
        <Stat label="Agents" value={stats.total_agents} />
      </div>

      <h3>By method</h3>
      <ul>
        {Object.entries(stats.by_method).map(([k, v]) => <li key={k}>{k}: {v}</li>)}
      </ul>

      <h3>By status</h3>
      <ul>
        {Object.entries(stats.by_status).map(([k, v]) => <li key={k}>{k}: {v}</li>)}
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ padding: 16, background: "#f9fafb", borderRadius: 8 }}>
      <div style={{ fontSize: 28, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 12, color: "#6b7280" }}>{label}</div>
    </div>
  );
}
