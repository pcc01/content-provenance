import { useEffect, useState } from "react";
import {
  api, provJsonDownloadUrl, provNDownloadUrl, xliffDownloadUrl,
  type DeploymentRecord, type LineageGraph, type ProvenanceResponse,
} from "../api/client";

// Phase 17 — this used to be a read-only summary of the PROV record
// (agents/activities/entities/relation-type list) with no way to reach the
// exports the backend already generates from that same record (lineage
// graph, PROV-JSON, PROV-N) or the deployment history captured on it —
// all three existed as working endpoints with zero UI. Added here rather
// than a new tab since they're all views ON the provenance record this
// panel already fetched, not a separate concern.
export function ProvenancePanel({
  unitId, provenance, deployments,
}: {
  unitId: string;
  provenance: ProvenanceResponse["provenance"];
  deployments: DeploymentRecord[];
}) {
  const [lineage, setLineage] = useState<LineageGraph | null>(null);
  const [lineageError, setLineageError] = useState<string | null>(null);

  useEffect(() => {
    setLineage(null);
    setLineageError(null);
    api.getLineage(unitId).then(setLineage).catch((e) => setLineageError(e instanceof Error ? e.message : String(e)));
  }, [unitId]);

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

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Lineage graph</div>
        {lineageError && <div style={{ color: "#b91c1c" }}>{lineageError}</div>}
        {!lineage && !lineageError && <div style={{ color: "#9ca3af" }}>Loading…</div>}
        {lineage && (
          <div style={{ color: "#374151" }}>
            {lineage.nodes.length} node(s), {lineage.edges.length} edge(s)
            <details style={{ marginTop: 4 }}>
              <summary style={{ cursor: "pointer", color: "#6b7280" }}>Show edges</summary>
              <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
                {lineage.edges.map((e, i) => (
                  <li key={i} style={{ color: "#6b7280" }}>
                    {e.label}: {e.from.split(":").slice(0, 2).join(":")} → {e.to.split(":").slice(0, 2).join(":")}
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )}
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Deployments ({deployments.length})</div>
        {deployments.length === 0 ? (
          <div style={{ color: "#9ca3af" }}>Not recorded as deployed anywhere yet.</div>
        ) : (
          deployments.map((d) => (
            <div key={d.id} style={{ color: "#374151", marginBottom: 2 }}>
              <strong>{d.context}</strong> — {d.location}
              <span style={{ color: "#9ca3af" }}> · {new Date(d.deployed_at).toLocaleDateString()}{!d.is_active && " · retired"}</span>
            </div>
          ))
        )}
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Export this unit</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 6 }}>
          <a href={xliffDownloadUrl(unitId)} target="_blank" rel="noreferrer">Download XLIFF 2.0 (with embedded PROV) →</a>
          <a href={provJsonDownloadUrl(unitId)} target="_blank" rel="noreferrer">Download PROV-JSON →</a>
          <a href={provNDownloadUrl(unitId)} target="_blank" rel="noreferrer">Download PROV-N →</a>
        </div>
        <XliffPreview unitId={unitId} />
      </div>
    </div>
  );
}

function XliffPreview({ unitId }: { unitId: string }) {
  const [xliff, setXliff] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (xliff !== null) return; // already loaded — <details> just toggles visibility
    setBusy(true);
    try {
      setXliff((await api.xliffPreview(unitId)).xliff);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details onToggle={(e) => e.currentTarget.open && load()}>
      <summary style={{ cursor: "pointer", color: "#6b7280" }}>Preview XLIFF (no download)</summary>
      {busy && <div style={{ color: "#9ca3af", marginTop: 4 }}>Loading…</div>}
      {xliff && (
        <pre style={{
          marginTop: 6, padding: 8, background: "#f9fafb", borderRadius: 6, fontSize: 11,
          maxHeight: 240, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all",
        }}>
          {xliff}
        </pre>
      )}
    </details>
  );
}
