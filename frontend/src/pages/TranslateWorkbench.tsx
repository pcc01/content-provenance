import { useEffect, useMemo, useState } from "react";
import {
  api, documentExportUrl, documentXliffUrl, TRANSLATE_PROVIDERS,
  type DocumentMeta, type StyleGuide, type TranslationUnit,
} from "../api/client";
import { LocaleSelect } from "../components/LocaleSelect";
import { ModelPicker } from "../components/ModelPicker";
import { PageIntro } from "../components/PageIntro";
import { QualityBadge } from "../components/QualityBadge";

// Step 1 of the pipeline (translate → evaluate → report → redrive): pick a
// source (pasted copy / existing untranslated units / an imported document),
// pick the engine, translate, then review inline — edit each target, accept a
// TM suggestion, approve per paragraph or the whole document — and assemble
// the result as one XLIFF 2.0.

type SourceMode = "paste" | "units" | "document";
type Segmentation = "paragraph" | "document";

function tmMatch(u: TranslationUnit): number | null {
  const v = u.metadata?.tm_match;
  return typeof v === "number" ? v : null;
}
function mtSuggestion(u: TranslationUnit): string | null {
  const v = u.metadata?.mt_suggestion;
  return typeof v === "string" ? v : null;
}

function scoreColor(s: number | null | undefined): string {
  if (s === null || s === undefined) return "#e5e7eb";
  if (s < 50) return "#e5484d";
  if (s < 80) return "#f5a524";
  return "#30a46c";
}

export function TranslateWorkbench() {
  const [sourceMode, setSourceMode] = useState<SourceMode>("paste");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // shared options
  const [sourceLanguage, setSourceLanguage] = useState("en-US");
  const [targetLanguage, setTargetLanguage] = useState("fr-FR");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [styleGuideId, setStyleGuideId] = useState("");
  const [segmentation, setSegmentation] = useState<Segmentation>("paragraph");
  const [guides, setGuides] = useState<StyleGuide[]>([]);
  const [reviewer, setReviewer] = useState("reviewer@example.com");
  const [tmxNote, setTmxNote] = useState<string | null>(null);

  // paste
  const [title, setTitle] = useState("");
  const [pasteText, setPasteText] = useState("");

  // units
  const [pendingUnits, setPendingUnits] = useState<TranslationUnit[]>([]);
  const [selectedUnitIds, setSelectedUnitIds] = useState<Set<string>>(new Set());

  // document
  const [docs, setDocs] = useState<DocumentMeta[]>([]);
  const [pickDocId, setPickDocId] = useState("");
  const [appendText, setAppendText] = useState("");

  // results / review
  const [docId, setDocId] = useState<string | null>(null);
  const [docMeta, setDocMeta] = useState<DocumentMeta | null>(null);
  const [segments, setSegments] = useState<TranslationUnit[]>([]);
  const [scores, setScores] = useState<Record<string, number | null>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [savingId, setSavingId] = useState<string | null>(null);

  useEffect(() => { api.listStyleGuides().then(setGuides).catch(() => {}); }, []);
  useEffect(() => { api.listDocuments().then(setDocs).catch(() => {}); }, []);

  const engineBody = () => ({
    provider: provider || undefined, model: model || undefined,
    style_guide_id: styleGuideId || undefined,
  });

  function resetReview() {
    setSegments([]); setScores({}); setEdits({}); setApproved(new Set());
    setDocId(null); setDocMeta(null);
  }

  async function loadScores(units: TranslationUnit[]) {
    const ids = units.map((u) => u.id);
    if (!ids.length) return;
    try {
      const batch = await api.getTranslationsBatch(ids);
      setScores(Object.fromEntries(batch.map((b) => [b.id, b.latest_score])));
    } catch { /* scores are best-effort */ }
  }

  async function loadDocSegments(id: string) {
    const res = await api.getDocumentSegments(id, targetLanguage);
    setDocId(id);
    setDocMeta(res.document);
    setSegments(res.segments);
    setEdits({});
    setApproved(new Set());
    const seg = (res.document.metadata?.segmentation as Segmentation | undefined);
    if (seg === "paragraph" || seg === "document") setSegmentation(seg);
    await loadScores(res.segments);
  }

  async function runPasteTranslate() {
    if (!pasteText.trim()) return;
    setBusy(true); setError(null);
    try {
      const doc = await api.createTextDocument({
        title: title.trim() || "Untitled", source_language: sourceLanguage,
        target_language: targetLanguage, text: pasteText, method: "ai",
        segmentation, ...engineBody(),
      });
      await loadDocSegments(doc.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function loadPendingUnits() {
    setBusy(true); setError(null);
    try {
      setPendingUnits(await api.listTranslations({
        status: "pending", target_language: targetLanguage, limit: 100,
      }));
      setSelectedUnitIds(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function runUnitsTranslate() {
    if (!selectedUnitIds.size) return;
    setBusy(true); setError(null);
    try {
      const out: TranslationUnit[] = [];
      for (const id of selectedUnitIds) {
        out.push(await api.translateUnitInPlace(id, engineBody()));
      }
      resetReview();
      setSegments(out);
      await loadScores(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function appendSegments() {
    if (!docId || !appendText.trim()) return;
    setBusy(true); setError(null);
    try {
      const res = await api.appendDocumentSegments(docId, { text: appendText, ...engineBody() });
      setSegments(res.segments);
      setAppendText("");
      await loadScores(res.segments);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function saveRow(u: TranslationUnit): Promise<TranslationUnit> {
    const next = edits[u.id];
    if (next === undefined || next === u.target_text) return u;
    setSavingId(u.id);
    try {
      const updated = await api.updateTranslationTarget(u.id, next, reviewer);
      setSegments((cur) => cur.map((s) => (s.id === updated.id ? updated : s)));
      setEdits(({ [u.id]: _drop, ...rest }) => rest);
      return updated;
    } finally { setSavingId(null); }
  }

  async function approveRow(u: TranslationUnit) {
    setError(null);
    try {
      await saveRow(u);
      await api.markReviewed(u.id, reviewer);
      setApproved((s) => new Set(s).add(u.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function approveAll() {
    setBusy(true); setError(null);
    try {
      for (const u of segments) {
        await saveRow(u);
        await api.markReviewed(u.id, reviewer);
      }
      setApproved(new Set(segments.map((s) => s.id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function handleTmxUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setTmxNote(null); setError(null);
    try {
      const r = await api.importTmx(file, {
        source_language: sourceLanguage, target_language: targetLanguage, source_system: "workbench",
      });
      setTmxNote(`${r.imported_count} TM pair(s) loaded — near-exact matches will pre-fill as a suggestion.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      e.target.value = "";
    }
  }

  const belowCount = useMemo(
    () => Object.values(scores).filter((s) => s !== null && s < 80).length,
    [scores],
  );
  const collapsed = segmentation === "document";

  function Row({ u, last }: { u: TranslationUnit; last: boolean }) {
    const score = scores[u.id] ?? null;
    const value = edits[u.id] ?? u.target_text ?? "";
    const dirty = edits[u.id] !== undefined && edits[u.id] !== u.target_text;
    const tm = tmMatch(u);
    const mt = mtSuggestion(u);
    const isApproved = approved.has(u.id);
    return (
      <div style={{
        display: "flex", gap: 0,
        borderBottom: last || collapsed ? "none" : "1px solid #f3f4f6",
        background: isApproved ? "#f0fdf4" : undefined,
      }}>
        <div style={{ width: 4, background: scoreColor(score), flexShrink: 0 }} />
        <div style={{
          flex: 1, padding: "8px 12px", fontSize: 13, color: "#374151",
          borderRight: "1px solid #f3f4f6", whiteSpace: "pre-wrap",
        }}>
          {u.source_text}
        </div>
        <div style={{ flex: 1, padding: "8px 12px", fontSize: 13 }}>
          <textarea
            value={value}
            onChange={(ev) => setEdits((m) => ({ ...m, [u.id]: ev.target.value }))}
            rows={Math.max(2, Math.ceil(value.length / 80))}
            style={{ width: "100%", fontSize: 13, padding: 6, boxSizing: "border-box", fontFamily: "inherit" }}
          />
          <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <QualityBadge score={score} />
            {tm !== null && (
              <span style={{ fontSize: 11, color: "#1e40af", background: "#eff6ff", padding: "1px 5px", borderRadius: 4 }}>
                TM {Math.round(tm * 100)}%
              </span>
            )}
            {mt && value !== mt && (
              <button onClick={() => setEdits((m) => ({ ...m, [u.id]: mt }))}
                      style={{ fontSize: 11, cursor: "pointer" }}>
                use MT suggestion
              </button>
            )}
            {!collapsed && (
              <>
                <button disabled={!dirty || savingId === u.id} onClick={() => saveRow(u)}
                        style={{ fontSize: 11, cursor: dirty ? "pointer" : "default" }}>
                  {savingId === u.id ? "Saving…" : "Save"}
                </button>
                <button disabled={isApproved} onClick={() => approveRow(u)}
                        style={{ fontSize: 11, cursor: isApproved ? "default" : "pointer" }}>
                  {isApproved ? "Approved" : "Approve"}
                </button>
              </>
            )}
            <span style={{ fontFamily: "monospace", fontSize: 10, color: "#9ca3af" }}>{u.id.slice(0, 8)}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, maxWidth: 1040 }}>
      <PageIntro
        title="Translate"
        requires="pick a source below (paste text, existing untranslated units, or an imported document), choose an engine, then Translate — the result opens in an inline review grid you can edit and approve."
      >
        Step 1 of the pipeline. Paragraph-level segmentation (never by sentence); load a TMX so
        near-exact matches pre-fill as a suggestion; assemble the reviewed segments as one XLIFF 2.0.
      </PageIntro>

      {error && (
        <div style={{ marginBottom: 16, padding: "8px 12px", background: "#fef2f2", color: "#b91c1c", borderRadius: 6, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* ── Options bar ─────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 14 }}>
        <LocaleSelect value={sourceLanguage} onChange={setSourceLanguage} label="Source" width={130} />
        <LocaleSelect value={targetLanguage} onChange={setTargetLanguage} label="Target" width={130} />
        <ModelPicker
          providers={TRANSLATE_PROVIDERS} provider={provider} model={model}
          onProviderChange={setProvider} onModelChange={setModel} label="Translate with"
        />
        <label style={{ fontSize: 13 }}>
          Style guide
          <select value={styleGuideId} onChange={(e) => setStyleGuideId(e.target.value)}
                  style={{ display: "block", padding: 4, marginTop: 4, minWidth: 170 }}>
            <option value="">None</option>
            {guides.map((g) => <option key={g.id} value={g.id}>{g.name} v{g.version}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 13 }}>
          Review by
          <select value={segmentation} onChange={(e) => setSegmentation(e.target.value as Segmentation)}
                  style={{ display: "block", padding: 4, marginTop: 4, minWidth: 130 }}>
            <option value="paragraph">Paragraph</option>
            <option value="document">Whole document</option>
          </select>
        </label>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16, fontSize: 12.5, color: "#6b7280" }}>
        <span>Translation memory:</span>
        <input type="file" accept=".tmx,application/xml,text/xml" onChange={handleTmxUpload} />
        {tmxNote && <span style={{ color: "#166534" }}>{tmxNote}</span>}
      </div>

      {/* ── Source mode ────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {(["paste", "units", "document"] as SourceMode[]).map((m) => (
          <button key={m} onClick={() => setSourceMode(m)}
                  style={{
                    padding: "5px 12px", fontSize: 13, cursor: "pointer", borderRadius: 6,
                    border: "1px solid #d1d5db",
                    background: sourceMode === m ? "#111827" : "#fff",
                    color: sourceMode === m ? "#fff" : "#374151",
                  }}>
            {m === "paste" ? "Paste text" : m === "units" ? "From units" : "Existing document"}
          </button>
        ))}
      </div>

      {sourceMode === "paste" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Document title"
                 style={{ padding: 6, fontSize: 13, maxWidth: 360 }} />
          <textarea value={pasteText} onChange={(e) => setPasteText(e.target.value)} rows={6}
                    placeholder="Paste copy here — blank lines separate paragraphs / segments…"
                    style={{ width: "100%", padding: 10, fontSize: 14, boxSizing: "border-box" }} />
          <div>
            <button disabled={busy || !pasteText.trim()} onClick={runPasteTranslate}
                    style={{ padding: "7px 16px", cursor: "pointer", fontWeight: 600 }}>
              {busy ? "Translating…" : "Translate →"}
            </button>
          </div>
        </div>
      )}

      {sourceMode === "units" && (
        <div style={{ marginBottom: 20 }}>
          <button disabled={busy} onClick={loadPendingUnits} style={{ padding: "6px 14px", cursor: "pointer" }}>
            {busy ? "Loading…" : `Load pending ${targetLanguage} units`}
          </button>
          {pendingUnits.length > 0 && (
            <div style={{ marginTop: 10, border: "1px solid #e5e7eb", borderRadius: 6, maxHeight: 260, overflowY: "auto" }}>
              {pendingUnits.map((u) => (
                <label key={u.id} style={{
                  display: "flex", gap: 8, padding: "6px 10px", fontSize: 12.5,
                  borderBottom: "1px solid #f3f4f6", cursor: "pointer",
                }}>
                  <input type="checkbox" checked={selectedUnitIds.has(u.id)}
                         onChange={(e) => setSelectedUnitIds((s) => {
                           const n = new Set(s);
                           e.target.checked ? n.add(u.id) : n.delete(u.id);
                           return n;
                         })} />
                  <span style={{ color: "#374151" }}>{u.source_text.slice(0, 140)}</span>
                </label>
              ))}
            </div>
          )}
          {pendingUnits.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <button disabled={busy || !selectedUnitIds.size} onClick={runUnitsTranslate}
                      style={{ padding: "7px 16px", cursor: "pointer", fontWeight: 600 }}>
                {busy ? "Translating…" : `Translate ${selectedUnitIds.size} selected`}
              </button>
            </div>
          )}
        </div>
      )}

      {sourceMode === "document" && (
        <div style={{ marginBottom: 20, display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13 }}>
            Document
            <select value={pickDocId} onChange={(e) => setPickDocId(e.target.value)}
                    style={{ display: "block", padding: 4, marginTop: 4, minWidth: 300 }}>
              <option value="">Select an imported document…</option>
              {docs.map((d) => <option key={d.id} value={d.id}>{d.title} ({d.format})</option>)}
            </select>
          </label>
          <button disabled={busy || !pickDocId} onClick={() => loadDocSegments(pickDocId)}
                  style={{ padding: "6px 14px", cursor: "pointer" }}>
            {busy ? "Loading…" : "Load"}
          </button>
        </div>
      )}

      {/* ── Review grid ────────────────────────────────────────────── */}
      {segments.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 13, color: "#6b7280", display: "flex", gap: 12, alignItems: "center" }}>
            <span>{segments.length} segment(s) · {sourceLanguage} → {targetLanguage}</span>
            {belowCount > 0 && <strong style={{ color: "#e5484d" }}>{belowCount} below 80</strong>}
            <label style={{ marginLeft: "auto" }}>
              as <input value={reviewer} onChange={(e) => setReviewer(e.target.value)}
                        style={{ fontSize: 12, padding: 3, width: 200 }} />
            </label>
          </div>

          <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ display: "flex", background: "#f9fafb", fontSize: 12, fontWeight: 600, color: "#6b7280" }}>
              <div style={{ width: 4, flexShrink: 0 }} />
              <div style={{ flex: 1, padding: "6px 12px", borderRight: "1px solid #f3f4f6" }}>Source</div>
              <div style={{ flex: 1, padding: "6px 12px" }}>Target ({targetLanguage})</div>
            </div>
            {segments.map((u, i) => <Row key={u.id} u={u} last={i === segments.length - 1} />)}
          </div>

          {collapsed && (
            <div>
              <button disabled={busy} onClick={approveAll}
                      style={{ padding: "7px 16px", cursor: "pointer", fontWeight: 600 }}>
                {busy ? "Working…" : `Approve all ${segments.length} segment(s)`}
              </button>
            </div>
          )}

          {docId && (
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 4 }}>
              <textarea value={appendText} onChange={(e) => setAppendText(e.target.value)} rows={2}
                        placeholder="Append more text to this document…"
                        style={{ flex: 1, padding: 8, fontSize: 13 }} />
              <button disabled={busy || !appendText.trim()} onClick={appendSegments}
                      style={{ padding: "6px 12px", cursor: "pointer" }}>
                Append
              </button>
            </div>
          )}

          {docId && (
            <div style={{ display: "flex", gap: 14, fontSize: 13, marginTop: 4, flexWrap: "wrap" }}>
              <a href={documentXliffUrl(docId, targetLanguage)}>Export XLIFF 2.0</a>
              {docMeta?.format === "docx" && (
                <a href={documentExportUrl(docId, "docx", targetLanguage)}>Export .docx</a>
              )}
              <span style={{ color: "#9ca3af" }}>
                document <span style={{ fontFamily: "monospace" }}>{docId.slice(0, 8)}</span> — score it in
                Quality Review → Redrive
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
