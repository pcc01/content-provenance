import { useEffect, useState } from "react";
import { api, type PageDiffChange } from "../api/client";

interface Props {
  url: string;
  targetLanguage: string;
  activeAsOf: string | null;
  onLoadAsOf: (asOf: string | null) => void;
  // The actual fetch (Playwright navigation + harvest) takes several
  // seconds — this only goes true once the overlay's tu:ready message
  // confirms the page and its snapshot actually exist, so history doesn't
  // 404 by asking before the fetch it depends on has finished.
  ready: boolean;
}

// Phase 9: browse a fetch+rewrite page's history. Timestamps come from
// TranslationUnitVersion's existing per-segment commit log (see
// app/core/page_history.py) — there's no separate "snapshot browser," this
// is just a UI over that timeline.
export function PageHistory({ url, targetLanguage, activeAsOf, onLoadAsOf, ready }: Props) {
  const [timestamps, setTimestamps] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fromTs, setFromTs] = useState("");
  const [toTs, setToTs] = useState("");
  const [diff, setDiff] = useState<PageDiffChange[] | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);

  useEffect(() => {
    setTimestamps(null);
    setDiff(null);
    setError(null);
    if (!ready) return;
    api.getPageHistory(url, targetLanguage)
      .then((h) => {
        setTimestamps(h.timestamps);
        if (h.timestamps.length >= 2) {
          setFromTs(h.timestamps[0]);
          setToTs(h.timestamps[h.timestamps.length - 1]);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [url, targetLanguage, ready]);

  async function showDiff() {
    if (!fromTs || !toTs) return;
    setDiffBusy(true);
    setError(null);
    try {
      const result = await api.getPageDiff(url, targetLanguage, fromTs, toTs);
      setDiff(result.changes);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDiffBusy(false);
    }
  }

  if (!ready) {
    return <div style={{ fontSize: 12, color: "#9ca3af" }}>History available once the page finishes loading…</div>;
  }
  if (error) {
    return <div style={{ fontSize: 12, color: "#b91c1c" }}>{error}</div>;
  }
  if (timestamps === null) {
    return <div style={{ fontSize: 12, color: "#9ca3af" }}>Loading history…</div>;
  }
  if (timestamps.length === 0) {
    return null;
  }

  return (
    <div style={{ borderTop: "1px solid #e5e7eb", paddingTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 600 }}>History ({timestamps.length})</div>

      <div style={{ display: "flex", gap: 6 }}>
        <select
          value={activeAsOf ?? ""}
          onChange={(e) => onLoadAsOf(e.target.value || null)}
          style={{ flex: 1, fontSize: 12, padding: 4 }}
        >
          <option value="">Latest</option>
          {timestamps.map((t) => (
            <option key={t} value={t}>{new Date(t).toLocaleString()}</option>
          ))}
        </select>
      </div>
      {activeAsOf && (
        <div style={{ fontSize: 11, color: "#9ca3af" }}>
          Viewing a past version — edits/redrive act on segment data, not this snapshot.
        </div>
      )}

      {timestamps.length >= 2 && (
        <>
          <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4 }}>Compare</div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <select value={fromTs} onChange={(e) => setFromTs(e.target.value)} style={{ flex: 1, fontSize: 11, padding: 3 }}>
              {timestamps.map((t) => (
                <option key={t} value={t}>{new Date(t).toLocaleString()}</option>
              ))}
            </select>
            <span style={{ fontSize: 11, color: "#9ca3af" }}>→</span>
            <select value={toTs} onChange={(e) => setToTs(e.target.value)} style={{ flex: 1, fontSize: 11, padding: 3 }}>
              {timestamps.map((t) => (
                <option key={t} value={t}>{new Date(t).toLocaleString()}</option>
              ))}
            </select>
          </div>
          <button onClick={showDiff} disabled={diffBusy} style={{ fontSize: 12, padding: "4px 0", cursor: "pointer" }}>
            {diffBusy ? "Comparing…" : "Show diff"}
          </button>
        </>
      )}

      {diff !== null && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
          {diff.length === 0 ? (
            <div style={{ fontSize: 12, color: "#9ca3af" }}>No changes between these two points.</div>
          ) : (
            diff.map((c) => (
              <div key={c.unit_id} style={{ fontSize: 11, background: "#f9fafb", padding: 6, borderRadius: 4 }}>
                <div style={{ color: "#9ca3af", marginBottom: 2 }}>{c.source_text}</div>
                <div style={{ color: "#b91c1c", textDecoration: "line-through" }}>{c.before_text ?? "(none)"}</div>
                <div style={{ color: "#15803d" }}>{c.after_text ?? "(none)"}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
