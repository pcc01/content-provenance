import { useEffect, useMemo, useRef, useState } from "react";
import {
  api, documentExportUrl,
  type DeckPage, type DeckShape, type DocumentMeta, type DocumentStructure,
} from "../api/client";
import { initReviewOverlay } from "../../review-sdk/overlay";
import { LocaleSelect } from "../components/LocaleSelect";
import { PageIntro } from "../components/PageIntro";
import { QualityBadge } from "../components/QualityBadge";

// Phase 8 — layout-aware slide-deck review. The deck's structure (slides +
// per-shape fractional bboxes) comes from GET /documents/{id}/structure;
// each text shape is rendered as an absolutely-positioned [data-tu-id]
// element, and the SAME rect-based overlay the inline review uses
// (initReviewOverlay) draws score-coloured boxes over them — no overlay
// changes, just a different page under it.

function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#c9ced6";
  if (score < 50) return "#e5484d";
  if (score < 80) return "#f5a524";
  return "#30a46c";
}

function expansionPct(shape: DeckShape): number | null {
  const src = shape.unit?.source_text?.length ?? 0;
  const tgt = shape.unit?.target_text?.length ?? 0;
  if (!src || !tgt) return null;
  return Math.round(((tgt - src) / src) * 100);
}

export function DeckReview() {
  const [docs, setDocs] = useState<DocumentMeta[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [locale, setLocale] = useState("fr-FR");
  const [structure, setStructure] = useState<DocumentStructure | null>(null);
  const [scores, setScores] = useState<Record<string, number | null>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [activeSlide, setActiveSlide] = useState(0);
  const [contactSheet, setContactSheet] = useState(false);
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listDocuments()
      .then((d) => setDocs(d.filter((x) => x.format === "pptx" || x.format === "pdf")))
      .catch(() => {});
  }, []);

  async function load() {
    if (!documentId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const s = await api.getDocumentStructure(documentId.trim(), locale);
      setStructure(s);
      setActiveSlide(0);
      setContactSheet(s.pages.length > 1);
      setSelectedUnitId(null);
      const unitIds = s.pages.flatMap((p) => p.shapes.map((sh) => sh.unit?.id).filter(Boolean) as string[]);
      if (unitIds.length) {
        const batch = await api.getTranslationsBatch(unitIds);
        setScores(Object.fromEntries(batch.map((b) => [b.id, b.latest_score])));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStructure(null);
    } finally {
      setLoading(false);
    }
  }

  // Draw the score overlay over the rendered slide, and listen for a box click.
  useEffect(() => {
    if (!structure || contactSheet) return;
    initReviewOverlay({ active: true });
    function onMsg(e: MessageEvent) {
      const m = e.data;
      if (m && typeof m === "object" && m.type === "tu:selected") setSelectedUnitId(m.tuId);
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [structure, contactSheet, activeSlide]);

  const worstBySlide = useMemo(() => {
    const m: Record<number, number | null> = {};
    for (const p of structure?.pages ?? []) {
      let worst: number | null = null;
      for (const sh of p.shapes) {
        const sc = sh.unit ? scores[sh.unit.id] ?? null : null;
        if (sc !== null && (worst === null || sc < worst)) worst = sc;
      }
      m[p.index] = worst;
    }
    return m;
  }, [structure, scores]);

  const issuesBySlide = useMemo(() => {
    const m: Record<number, number> = {};
    for (const p of structure?.pages ?? []) {
      m[p.index] = p.shapes.filter((sh) => {
        const sc = sh.unit ? scores[sh.unit.id] ?? null : null;
        return (sc !== null && sc < 80) || (expansionPct(sh) ?? 0) > 15;
      }).length;
    }
    return m;
  }, [structure, scores]);

  const selectedShape = useMemo(() => {
    if (!structure || !selectedUnitId) return null;
    for (const p of structure.pages) {
      for (const sh of p.shapes) if (sh.unit?.id === selectedUnitId) return sh;
    }
    return null;
  }, [structure, selectedUnitId]);

  function SlideThumb({ page, size }: { page: DeckPage; size: number }) {
    const ratio = page.height && page.width ? page.height / page.width : 0.5625;
    return (
      <div
        onClick={() => { setActiveSlide(page.index); setContactSheet(false); }}
        style={{
          position: "relative", width: size, height: size * ratio, background: "#fff",
          border: page.index === activeSlide ? "2px solid #111827" : "1px solid #d1d5db",
          borderRadius: 3, cursor: "pointer", flexShrink: 0, overflow: "hidden",
        }}
        title={`Slide ${page.index + 1}`}
      >
        {page.shapes.filter((s) => s.x !== null).map((s) => (
          <div key={s.id} style={{
            position: "absolute",
            left: `${(s.x ?? 0) * 100}%`, top: `${(s.y ?? 0) * 100}%`,
            width: `${(s.w ?? 0) * 100}%`, height: `${(s.h ?? 0) * 100}%`,
            background: scoreColor(s.unit ? scores[s.unit.id] : null), opacity: 0.65, borderRadius: 1,
          }} />
        ))}
        <div style={{ position: "absolute", bottom: 1, left: 3, fontSize: 9, color: "#6b7280" }}>
          {page.index + 1}
          {issuesBySlide[page.index] > 0 && (
            <span style={{ color: "#e5484d", fontWeight: 700 }}> · {issuesBySlide[page.index]}</span>
          )}
        </div>
      </div>
    );
  }

  const page = structure?.pages[activeSlide];
  const geomShapes = page?.shapes.filter((s) => s.x !== null && s.unit) ?? [];
  const noteShapes = page?.shapes.filter((s) => s.kind === "speaker_note") ?? [];
  const slideRatio = page && page.width && page.height ? page.height / page.width : 0.5625;

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <PageIntro
        title="Deck Review"
        requires="pick an imported .pptx or .pdf and a target language, then Load — each page renders with score-coloured boxes over its text, exactly like the inline review."
      >
        Review a slide deck or PDF in context: layout preserved, per-shape quality scores, and an expansion
        badge wherever the translated text has outgrown its box. For a .pptx you can export the translated
        deck back out with its layout intact.
      </PageIntro>

      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 16 }}>
        <label style={{ fontSize: 13 }}>
          Deck
          {docs.length > 0 ? (
            <select value={documentId} onChange={(e) => setDocumentId(e.target.value)}
                    style={{ display: "block", padding: 4, marginTop: 4, minWidth: 280 }}>
              <option value="">Select an imported .pptx…</option>
              {docs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
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
        {structure && structure.pages.length > 1 && (
          <button onClick={() => setContactSheet((v) => !v)} style={{ padding: "6px 14px", cursor: "pointer" }}>
            {contactSheet ? "Open slide view" : "Contact sheet"}
          </button>
        )}
        {structure?.document.format === "pptx" && (
          <a href={documentExportUrl(structure.document.id, "pptx", locale)} style={{ fontSize: 13, alignSelf: "center" }}>
            Export translated .pptx
          </a>
        )}
      </div>

      {error && (
        <div style={{ marginBottom: 16, padding: "8px 12px", background: "#fef2f2", color: "#b91c1c", borderRadius: 6, fontSize: 13 }}>
          {error}
        </div>
      )}

      {structure && contactSheet && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          {structure.pages.map((p) => <SlideThumb key={p.index} page={p} size={220} />)}
        </div>
      )}

      {structure && !contactSheet && page && (
        <div style={{ display: "flex", gap: 16 }}>
          {/* thumbnail rail */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 620, overflowY: "auto", paddingRight: 4 }}>
            {structure.pages.map((p) => <SlideThumb key={p.index} page={p} size={116} />)}
          </div>

          {/* slide canvas */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 6 }}>
              Slide {page.index + 1} of {structure.pages.length}
              {worstBySlide[page.index] !== null && <> · worst score {worstBySlide[page.index]}</>}
            </div>
            <div
              ref={canvasRef}
              style={{
                position: "relative", width: "100%", paddingTop: `${slideRatio * 100}%`,
                background: "#fff", border: "1px solid #d1d5db", borderRadius: 4,
              }}
            >
              {geomShapes.map((s) => {
                const exp = expansionPct(s);
                return (
                  <div
                    key={s.id}
                    data-tu-id={s.unit!.id}
                    style={{
                      position: "absolute",
                      left: `${(s.x ?? 0) * 100}%`, top: `${(s.y ?? 0) * 100}%`,
                      width: `${(s.w ?? 0) * 100}%`, height: `${(s.h ?? 0) * 100}%`,
                      fontSize: 11, lineHeight: 1.25, color: "#111827", overflow: "hidden",
                      padding: 2, boxSizing: "border-box",
                      fontWeight: s.kind === "title" ? 700 : 400,
                    }}
                  >
                    {s.unit!.target_text}
                    {exp !== null && exp > 15 && (
                      <span style={{
                        position: "absolute", right: 0, bottom: 0, fontSize: 9, fontWeight: 700,
                        color: "#fff", background: "#e5484d", padding: "0 3px", borderRadius: 2,
                      }}>
                        +{exp}%
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {noteShapes.length > 0 && (
              <div style={{ marginTop: 10, fontSize: 12, color: "#6b7280" }}>
                <strong>Speaker notes</strong>
                <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {noteShapes.map((s) => (
                    <li key={s.id} data-tu-id={s.unit?.id}>{s.unit?.target_text}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* selected-segment panel */}
          <div style={{ width: 280, flexShrink: 0, fontSize: 13 }}>
            {selectedShape?.unit ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <QualityBadge score={scores[selectedShape.unit.id] ?? null} />
                  <span style={{ color: "#6b7280" }}>{selectedShape.kind}</span>
                </div>
                <div>
                  <div style={{ color: "#9ca3af", fontSize: 11 }}>Source</div>
                  <div>{selectedShape.unit.source_text}</div>
                </div>
                <div>
                  <div style={{ color: "#9ca3af", fontSize: 11 }}>Target ({locale})</div>
                  <div>{selectedShape.unit.target_text}</div>
                </div>
                <div style={{ fontFamily: "monospace", fontSize: 11, color: "#9ca3af" }}>
                  {selectedShape.unit.id}
                </div>
              </div>
            ) : (
              <div style={{ color: "#9ca3af" }}>Click a highlighted shape to inspect it.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
