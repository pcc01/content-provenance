import { useEffect, useMemo, useState } from "react";
import {
  api, documentExportUrl,
  type DocumentMeta, type DocumentSegments, type TranslationUnit,
} from "../api/client";
import { LocaleSelect } from "../components/LocaleSelect";
import { PageIntro } from "../components/PageIntro";
import { QualityBadge } from "../components/QualityBadge";

// Phase 7 — the bilingual-reader view for flow documents (DOCX / plain
// text / Markdown / CSV), where there's no page geometry to preserve. Source
// and target aligned in reading order, score heat down the side, inline peek
// at each block. Round-trip export back to .docx keeps the styles.

function scoreColor(s: number | null | undefined): string {
  if (s === null || s === undefined) return "#e5e7eb";
  if (s < 50) return "#e5484d";
  if (s < 80) return "#f5a524";
  return "#30a46c";
}

export function DocumentReview() {
  const [docs, setDocs] = useState<DocumentMeta[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [locale, setLocale] = useState("fr-FR");
  const [data, setData] = useState<DocumentSegments | null>(null);
  const [scores, setScores] = useState<Record<string, number | null>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listDocuments()
      .then((d) => setDocs(d.filter((x) => ["docx", "text", "markdown", "csv"].includes(x.format))))
      .catch(() => {});
  }, []);

  async function load() {
    if (!documentId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getDocumentSegments(documentId.trim(), locale);
      setData(res);
      const ids = res.segments.map((s) => s.id);
      if (ids.length) {
        const batch = await api.getTranslationsBatch(ids);
        setScores(Object.fromEntries(batch.map((b) => [b.id, b.latest_score])));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  const belowCount = useMemo(
    () => Object.values(scores).filter((s) => s !== null && s < 80).length,
    [scores],
  );

  function Row({ seg }: { seg: TranslationUnit }) {
    const score = scores[seg.id] ?? null;
    return (
      <div style={{ display: "flex", gap: 0, borderBottom: "1px solid #f3f4f6" }}>
        <div style={{ width: 4, background: scoreColor(score), flexShrink: 0 }} />
        <div style={{ flex: 1, padding: "8px 12px", fontSize: 13, color: "#374151", borderRight: "1px solid #f3f4f6" }}>
          {seg.source_text}
        </div>
        <div style={{ flex: 1, padding: "8px 12px", fontSize: 13 }}>
          {seg.target_text}
          <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
            <QualityBadge score={score} />
            <span style={{ fontFamily: "monospace", fontSize: 10, color: "#9ca3af" }}>{seg.id.slice(0, 8)}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <PageIntro
        title="Document Review"
        requires="pick an imported .docx / .txt / .md / .csv and a target language, then Load — source and target line up block-by-block with a quality score per row."
      >
        The bilingual-reader view for flow documents (no page layout to preserve). For a .docx you can export
        the translated document back out with its styles intact.
      </PageIntro>

      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 16 }}>
        <label style={{ fontSize: 13 }}>
          Document
          {docs.length > 0 ? (
            <select value={documentId} onChange={(e) => setDocumentId(e.target.value)}
                    style={{ display: "block", padding: 4, marginTop: 4, minWidth: 280 }}>
              <option value="">Select an imported document…</option>
              {docs.map((d) => <option key={d.id} value={d.id}>{d.title} ({d.format})</option>)}
            </select>
          ) : (
            <input value={documentId} onChange={(e) => setDocumentId(e.target.value)}
                   placeholder="document id" style={{ display: "block", width: 280, marginTop: 4, padding: 4 }} />
          )}
        </label>
        <LocaleSelect value={locale} onChange={setLocale} label="Target language" width={180} />
        <button disabled={loading || !documentId.trim()} onClick={load} style={{ padding: "6px 14px", cursor: "pointer" }}>
          {loading ? "Loading…" : "Load"}
        </button>
        {data?.document.format === "docx" && (
          <a href={documentExportUrl(data.document.id, "docx", locale)} style={{ fontSize: 13, alignSelf: "center" }}>
            Export translated .docx
          </a>
        )}
      </div>

      {error && (
        <div style={{ marginBottom: 16, padding: "8px 12px", background: "#fef2f2", color: "#b91c1c", borderRadius: 6, fontSize: 13 }}>
          {error}
        </div>
      )}

      {data && (
        <>
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 8 }}>
            {data.segments.length} block(s) · {data.document.source_language} → {locale}
            {belowCount > 0 && <> · <strong style={{ color: "#e5484d" }}>{belowCount} below 80</strong></>}
          </div>
          <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ display: "flex", background: "#f9fafb", fontSize: 12, fontWeight: 600, color: "#6b7280" }}>
              <div style={{ width: 4, flexShrink: 0 }} />
              <div style={{ flex: 1, padding: "6px 12px", borderRight: "1px solid #f3f4f6" }}>Source</div>
              <div style={{ flex: 1, padding: "6px 12px" }}>Target ({locale})</div>
            </div>
            {data.segments.map((seg) => <Row key={seg.id} seg={seg} />)}
          </div>
        </>
      )}
    </div>
  );
}
