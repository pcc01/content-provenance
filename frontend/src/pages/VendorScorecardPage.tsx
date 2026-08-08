import { useEffect, useState } from "react";
import { api, vendorScorecardPdfUrl, type VendorScorecardEntry } from "../api/client";

function fmt(score: number | null): string {
  return score === null ? "—" : score.toFixed(1);
}

function scoreColor(score: number | null): string {
  if (score === null) return "#9ca3af";
  if (score < 70) return "#e5484d";
  if (score < 85) return "#f5a524";
  return "#30a46c";
}

// Phase 14 — ranks every vendor/AI agent by average quality + style
// scores, using each unit's LATEST score only. The artifact a PM actually
// uses in a vendor renegotiation, not per-segment QA.
export function VendorScorecardPage() {
  const [targetLanguage, setTargetLanguage] = useState("");
  const [entries, setEntries] = useState<VendorScorecardEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    try {
      setEntries(await api.getVendorScorecard(targetLanguage || undefined));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ padding: 24, maxWidth: 840 }}>
      <h2 style={{ marginTop: 0 }}>Vendor Scorecard</h2>
      <p style={{ color: "#6b7280" }}>
        Every organization with at least one scored translation — vendors and AI backends
        ranked on equal footing, best-first.
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 16 }}>
        <label style={{ fontSize: 13 }}>
          Target language (blank = all)
          <input value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)} placeholder="fr-FR"
                 style={{ display: "block", padding: 4, marginTop: 4, width: 140 }} />
        </label>
        <button onClick={refresh} style={{ padding: "6px 14px", cursor: "pointer" }}>Refresh</button>
        <a href={vendorScorecardPdfUrl(targetLanguage || undefined)} target="_blank" rel="noreferrer"
           style={{ padding: "6px 14px", fontSize: 13 }}>
          Download PDF report →
        </a>
      </div>

      {loading ? (
        <div style={{ color: "#9ca3af" }}>Loading…</div>
      ) : entries.length === 0 ? (
        <div style={{ color: "#9ca3af" }}>No scored translations yet for this scope.</div>
      ) : (
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 8px" }}>Vendor / Agent</th>
              <th style={{ padding: "6px 8px" }}>Units</th>
              <th style={{ padding: "6px 8px" }}>Quality</th>
              <th style={{ padding: "6px 8px" }}>Style</th>
              <th style={{ padding: "6px 8px" }}>Tone</th>
              <th style={{ padding: "6px 8px" }}>Voice</th>
              <th style={{ padding: "6px 8px" }}>Terminology</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.organization} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "6px 8px", fontWeight: 600 }}>{e.organization}</td>
                <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{e.unit_count}</td>
                <td style={{ padding: "6px 8px", color: scoreColor(e.avg_quality_score), fontVariantNumeric: "tabular-nums" }}>{fmt(e.avg_quality_score)}</td>
                <td style={{ padding: "6px 8px", color: scoreColor(e.avg_style_score), fontVariantNumeric: "tabular-nums" }}>{fmt(e.avg_style_score)}</td>
                <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{fmt(e.avg_tone_score)}</td>
                <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{fmt(e.avg_voice_score)}</td>
                <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{fmt(e.avg_terminology_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
