import { useState } from "react";
import { api, type ConsistencyFinding, type ConsistencyResult } from "../api/client";

const FINDING_LABEL: Record<ConsistencyFinding["finding_type"], string> = {
  term_drift: "Terminology drift",
  term_inconsistency: "Terminology inconsistency",
  tone_spread: "Tone inconsistency",
};

const SEVERITY_COLOR: Record<ConsistencyFinding["severity"], string> = {
  warning: "#f5a524",
  info: "#3b82f6",
};

// Phase 14 — clusters units by shared glossary term / style rule and
// compares only within each cluster (never a full pairwise scan), so a
// campaign spanning many pages reads as one voice, not just individually
// passing segments.
export function ConsistencyPage() {
  const [targetLanguage, setTargetLanguage] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ConsistencyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.checkConsistency({ target_language: targetLanguage || undefined }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 780 }}>
      <h2 style={{ marginTop: 0 }}>Cross-Document Consistency</h2>
      <p style={{ color: "#6b7280" }}>
        Does this term mean the same thing everywhere it's used? Does tone hold steady across
        every unit following the same style rule? Checked by clustering, not a full pairwise scan.
      </p>

      {error && <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>{error}</div>}

      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 20 }}>
        <label style={{ fontSize: 13 }}>
          Target language (blank = all)
          <input value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)} placeholder="fr-FR"
                 style={{ display: "block", padding: 4, marginTop: 4, width: 140 }} />
        </label>
        <button disabled={busy} onClick={run} style={{ padding: "6px 14px", cursor: "pointer" }}>
          {busy ? "Checking…" : "Run check"}
        </button>
      </div>

      {result && (
        <>
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
            {result.units_checked} unit(s) checked — {result.findings.length} finding(s)
          </div>
          {result.findings.length === 0 ? (
            <div style={{ padding: 12, background: "#f0fdf4", borderRadius: 6, fontSize: 13, color: "#166534" }}>
              No inconsistencies found in this scope.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {result.findings.map((f) => (
                <div key={f.id} style={{ padding: 10, border: "1px solid #e5e7eb", borderRadius: 6, fontSize: 13 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{
                      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
                      background: SEVERITY_COLOR[f.severity],
                    }} />
                    <strong>{FINDING_LABEL[f.finding_type]}</strong>
                    <span style={{ color: "#9ca3af" }}>· {f.unit_ids.length} unit(s)</span>
                  </div>
                  <div>{f.summary}</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
