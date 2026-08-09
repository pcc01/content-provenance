import { useEffect, useState } from "react";
import { api, type AutomaticMetricScore } from "../api/client";

// Phase 17 — GET /quality/{unit_id}/automatic existed with zero UI
// consumer since Phase 15 shipped it: this is the only place COMET-Kiwi/
// METEOR scores (recorded automatically on every redrive as a regression
// check, or via the batch admin COMET endpoint) are ever visible to a
// reviewer, as distinct from the LLM-judge MQM score shown elsewhere in
// the drawer (QualityBadge) — see docs/quality-evaluation-research.md for
// why these are kept as independent axes rather than blended into one number.
export function MetricsPanel({ unitId }: { unitId: string }) {
  const [scores, setScores] = useState<AutomaticMetricScore[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setScores(null);
    setError(null);
    api.getAutomaticScores(unitId).then(setScores).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [unitId]);

  if (error) return <div style={{ fontSize: 13, color: "#b91c1c" }}>{error}</div>;
  if (!scores) return <div style={{ fontSize: 13, color: "#9ca3af" }}>Loading…</div>;

  return (
    <div style={{ fontSize: 13 }}>
      <p style={{ color: "#6b7280", marginTop: 0 }}>
        Automatic (non-LLM) quality metrics — COMET-Kiwi and METEOR — a third scoring axis,
        independent of the MQM judge score shown above. METEOR is recorded automatically after
        every redrive, comparing the new text against the version it replaced.
      </p>
      {scores.length === 0 ? (
        <div style={{ color: "#9ca3af" }}>No automatic metric scores recorded for this unit yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "4px 6px" }}>Metric</th>
              <th style={{ padding: "4px 6px" }}>Score</th>
              <th style={{ padding: "4px 6px" }}>Reference</th>
              <th style={{ padding: "4px 6px" }}>Scored at</th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "4px 6px", fontWeight: 600 }}>{s.metric}</td>
                <td style={{ padding: "4px 6px", fontVariantNumeric: "tabular-nums" }}>
                  {s.score === null ? "—" : s.score.toFixed(1)}
                </td>
                <td style={{ padding: "4px 6px", color: "#9ca3af" }}>{s.reference_type ?? "none"}</td>
                <td style={{ padding: "4px 6px", color: "#9ca3af" }}>{new Date(s.scored_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
