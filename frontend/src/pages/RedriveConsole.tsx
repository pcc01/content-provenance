import { useState } from "react";
import { api, type RedrivePreview, type RedriveRun } from "../api/client";
import { QualityBadge } from "../components/QualityBadge";

export function RedriveConsole() {
  const [targetLanguage, setTargetLanguage] = useState("");
  const [threshold, setThreshold] = useState(80);
  const [requireApproval, setRequireApproval] = useState(false);
  const [preview, setPreview] = useState<RedrivePreview | null>(null);
  const [run, setRun] = useState<RedriveRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [actor, setActor] = useState("reviewer@example.com");

  async function doPreview() {
    setBusy(true);
    try {
      setPreview(await api.previewRedrive({ threshold, target_language: targetLanguage || undefined }));
    } finally {
      setBusy(false);
    }
  }

  async function doRun() {
    setBusy(true);
    try {
      const scope = targetLanguage ? { target_language: targetLanguage } : {};
      const result = await api.createRedriveRun({ threshold, scope, require_human_approval: requireApproval });
      setRun(result);
    } finally {
      setBusy(false);
    }
  }

  async function approve(itemId: string) {
    if (!run) return;
    await api.approveRedriveItem(run.id, itemId, actor);
    setRun(await api.getRedriveRun(run.id));
  }

  async function reject(itemId: string) {
    if (!run) return;
    await api.rejectRedriveItem(run.id, itemId, actor, "declined in review console");
    setRun(await api.getRedriveRun(run.id));
  }

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <h2 style={{ marginTop: 0 }}>Redrive Console</h2>
      <p style={{ color: "#6b7280" }}>
        Score everything in scope, then redrive whatever falls below the threshold. With human-in-the-loop
        enabled, redrives are proposed but not applied until approved below.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
        <label style={{ fontSize: 13 }}>
          Target language (blank = all)
          <input value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)}
                 placeholder="fr-FR" style={{ display: "block", width: 200, marginTop: 4, padding: 4 }} />
        </label>
        <label style={{ fontSize: 13 }}>
          Threshold: <strong>{threshold}</strong>
          <input type="range" min={0} max={100} value={threshold}
                 onChange={(e) => setThreshold(Number(e.target.value))} style={{ display: "block", width: 300 }} />
        </label>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={requireApproval} onChange={(e) => setRequireApproval(e.target.checked)} />
          Require human approval before applying redrives
        </label>
        <label style={{ fontSize: 13 }}>
          Approving/rejecting as
          <input value={actor} onChange={(e) => setActor(e.target.value)}
                 style={{ display: "block", width: 240, marginTop: 4, padding: 4 }} />
        </label>

        <div style={{ display: "flex", gap: 8 }}>
          <button disabled={busy} onClick={doPreview} style={{ padding: "6px 14px", cursor: "pointer" }}>
            Preview
          </button>
          <button disabled={busy} onClick={doRun} style={{ padding: "6px 14px", cursor: "pointer" }}>
            Run redrive
          </button>
        </div>
      </div>

      {preview && (
        <div style={{ marginBottom: 20, padding: 12, background: "#f9fafb", borderRadius: 6, fontSize: 13 }}>
          <div>{preview.scope_count} unit(s) in scope</div>
          <div><strong>{preview.below_threshold}</strong> would be redriven at threshold {threshold}</div>
          <div>~{preview.estimated_source_chars.toLocaleString()} source characters via {preview.redrive_provider}</div>
        </div>
      )}

      {run && (
        <div>
          <h3>Run {run.id.slice(0, 8)} — {run.status}</h3>
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 8 }}>
            {Object.entries(run.summary).map(([k, v]) => `${k}: ${v}`).join(" · ")}
          </div>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                <th>Unit</th><th>Before</th><th>After</th><th>Outcome</th><th></th>
              </tr>
            </thead>
            <tbody>
              {run.items.map((item) => (
                <tr key={item.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>{item.unit_id.slice(0, 8)}</td>
                  <td><QualityBadge score={item.before_score} /></td>
                  <td><QualityBadge score={item.after_score} /></td>
                  <td>{item.outcome}</td>
                  <td>
                    {item.outcome === "pending_approval" && (
                      <div style={{ display: "flex", gap: 4 }}>
                        <button onClick={() => approve(item.id)} style={{ cursor: "pointer", fontSize: 11 }}>Approve</button>
                        <button onClick={() => reject(item.id)} style={{ cursor: "pointer", fontSize: 11 }}>Reject</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
