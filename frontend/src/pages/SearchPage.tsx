import { useState } from "react";
import { api } from "../api/client";

interface SearchResult {
  translation_unit_id?: string;
  id?: string;
  source_text?: string;
  target_text?: string;
  translation_method?: string;
  score?: number;
  [key: string]: unknown;
}

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [semantic, setSemantic] = useState(true);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch() {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.search(query.trim(), semantic);
      setResults(res.results as SearchResult[]);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 800 }}>
      <h2 style={{ marginTop: 0 }}>Search</h2>
      <p style={{ color: "#6b7280" }}>
        Semantic (embedding) or keyword (BM25) search over all translated content, via the
        existing Haystack pipeline.
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input
          value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
          placeholder="Search translated content…"
          style={{ flex: 1, padding: 6, fontSize: 14 }}
        />
        <button onClick={runSearch} disabled={busy} style={{ padding: "6px 16px", cursor: "pointer" }}>Search</button>
      </div>
      <label style={{ fontSize: 12, color: "#6b7280", display: "flex", alignItems: "center", gap: 6, marginBottom: 16 }}>
        <input type="checkbox" checked={semantic} onChange={(e) => setSemantic(e.target.checked)} />
        Semantic search (uncheck for BM25 keyword search)
      </label>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      {total !== null && (
        <p style={{ fontSize: 12, color: "#6b7280" }}>{total} result(s)</p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {results.map((r, i) => (
          <div key={r.translation_unit_id ?? r.id ?? i} style={{ padding: 10, border: "1px solid #e5e7eb", borderRadius: 6, fontSize: 13 }}>
            {r.source_text && <div><strong>Source:</strong> {r.source_text}</div>}
            {r.target_text && <div><strong>Target:</strong> {r.target_text}</div>}
            <div style={{ color: "#9ca3af", fontSize: 11, marginTop: 4 }}>
              {r.translation_method && `method: ${r.translation_method}`}
              {typeof r.score === "number" && ` · score: ${r.score.toFixed(3)}`}
            </div>
          </div>
        ))}
        {results.length === 0 && total !== null && (
          <p style={{ color: "#9ca3af", fontSize: 13 }}>No results.</p>
        )}
      </div>
    </div>
  );
}
