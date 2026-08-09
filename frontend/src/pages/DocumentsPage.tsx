import { useState } from "react";
import { api, type DocumentMeta } from "../api/client";
import { LocaleSelect } from "../components/LocaleSelect";
import { PageIntro } from "../components/PageIntro";

// Upload a .txt/.md file for Phase 7a in-context review. There's no
// document list endpoint (out of scope for a first pass, same as
// ImageReview never got one) — after upload, this just hands back the
// ready-made URL/route/locale to paste into the Review tab's fields, since
// DocumentViewer is served from THIS app's own origin (see main.tsx).
export function DocumentsPage() {
  const [sourceLanguage, setSourceLanguage] = useState("en-US");
  const [targetLanguage, setTargetLanguage] = useState("fr-FR");
  const [method, setMethod] = useState("ai");
  const [title, setTitle] = useState("");
  // Phase 18 — CSV only; ignored (not an error) for .txt/.md uploads.
  const [sourceColumn, setSourceColumn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<DocumentMeta | null>(null);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setBusy(true);
    setUploaded(null);
    try {
      const doc = await api.importDocument(file, {
        source_language: sourceLanguage, target_language: targetLanguage, method, title: title || undefined,
        source_column: sourceColumn || undefined,
      });
      setUploaded(doc);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  const reviewRoute = uploaded ? `/documents/${uploaded.id}` : "";
  const reviewUrl = uploaded ? `${window.location.origin}${reviewRoute}?locale=${encodeURIComponent(targetLanguage)}&__review=1` : "";

  return (
    <div style={{ padding: 24, maxWidth: 640 }}>
      <PageIntro
        title="Documents"
        requires="choose a .txt, .md, or .csv file at the bottom of this form. Source/target language and method already have sensible defaults — adjust them first only if needed."
      >
        Upload a plain text (.txt), Markdown (.md), or CSV (.csv) file. Text/Markdown segment on
        blank lines (each paragraph/heading becomes its own unit); CSV segments one unit per row.
        Every segment is translated immediately and reviewable in-context in the Review tab — the
        document renders as its own page inside this app.
      </PageIntro>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 320, marginBottom: 20 }}>
        <LocaleSelect value={sourceLanguage} onChange={setSourceLanguage} label="Source language" width={280} />
        <LocaleSelect value={targetLanguage} onChange={setTargetLanguage} label="Target language" width={280} />
        <label style={{ fontSize: 13 }}>
          Method
          <select value={method} onChange={(e) => setMethod(e.target.value)} style={{ display: "block", width: "100%", padding: 4, boxSizing: "border-box" }}>
            <option value="ai">ai</option>
            <option value="human">human</option>
            <option value="hybrid">hybrid</option>
          </select>
        </label>
        <label style={{ fontSize: 13 }}>
          Title (optional — defaults to the filename)
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ display: "block", width: "100%", padding: 4, boxSizing: "border-box" }} />
        </label>
        <label style={{ fontSize: 13 }}>
          Source column (CSV only, optional — defaults to the first column)
          <input value={sourceColumn} onChange={(e) => setSourceColumn(e.target.value)} placeholder="e.g. source_text"
                 style={{ display: "block", width: "100%", padding: 4, boxSizing: "border-box" }} />
        </label>
      </div>

      <input type="file" accept=".txt,.md,.markdown,.csv,text/plain,text/markdown,text/csv" disabled={busy} onChange={handleUpload} />

      {uploaded && (
        <div style={{ marginTop: 24, padding: 16, background: "#f0fdf4", borderRadius: 8, border: "1px solid #bbf7d0" }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Imported "{uploaded.title}"</div>
          <div style={{ fontSize: 13, color: "#374151", marginBottom: 12 }}>
            {uploaded.format} · {uploaded.source_language} → {targetLanguage} · id: {uploaded.id}
          </div>
          <div style={{ fontSize: 13, color: "#374151", marginBottom: 4 }}>
            To review it, open the <strong>Review</strong> tab and set:
          </div>
          <table style={{ fontSize: 12, borderCollapse: "collapse" }}>
            <tbody>
              <tr>
                <td style={{ color: "#6b7280", paddingRight: 8 }}>Target app base URL</td>
                <td><code>{window.location.origin}</code></td>
              </tr>
              <tr>
                <td style={{ color: "#6b7280", paddingRight: 8 }}>Route</td>
                <td><code>{reviewRoute}</code></td>
              </tr>
              <tr>
                <td style={{ color: "#6b7280", paddingRight: 8 }}>Locale</td>
                <td><code>{targetLanguage}</code></td>
              </tr>
            </tbody>
          </table>
          <div style={{ marginTop: 12 }}>
            <a href={reviewUrl} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
              Open the rendered document directly →
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
