import type { ProvenanceResponse } from "../api/client";

export function ProvenancePanel({ provenance }: { provenance: ProvenanceResponse["provenance"] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 13 }}>
      {provenance.summary && (
        <p style={{ color: "#374151", fontStyle: "italic" }}>{provenance.summary}</p>
      )}

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Agents</div>
        {provenance.agents.map((a) => (
          <div key={a.id} style={{ display: "flex", gap: 6, color: "#374151" }}>
            <span>{a.name}</span>
            <span style={{ color: "#9ca3af" }}>({a.agent_type}{a.organization ? ` · ${a.organization}` : ""})</span>
          </div>
        ))}
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Activities</div>
        {provenance.activities.map((act) => (
          <div key={act.id} style={{ color: "#374151" }}>
            {act.activity_type} — {new Date(act.started_at).toLocaleString()}
          </div>
        ))}
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Entities</div>
        {provenance.entities.map((e) => (
          <div key={e.id} style={{ color: "#374151" }}>{e.entity_type}</div>
        ))}
      </div>

      <details>
        <summary style={{ cursor: "pointer", color: "#6b7280" }}>
          Relations ({provenance.relations.length})
        </summary>
        <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
          {provenance.relations.map((rel, i) => (
            <li key={i} style={{ color: "#6b7280" }}>{rel.type}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
