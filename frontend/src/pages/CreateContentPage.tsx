import { useEffect, useState } from "react";
import {
  api, TRANSLATE_PROVIDERS, type CheckSourceResult, type RetrievePreview, type StyleGuide, type TranslateResponse,
} from "../api/client";
import { LocaleSelect } from "../components/LocaleSelect";
import { ModelPicker } from "../components/ModelPicker";
import { PageIntro } from "../components/PageIntro";

// Phase 13/9b.5 — the actual start of the Content Creation workflow: write
// (or paste) new source copy, check it against brand voice BEFORE
// translation (catching an off-brand draft is cheaper than catching it
// after it's shipped in twelve languages), preview what context an AI
// translation would retrieve, then submit for translation with full
// provenance/redrive/review treatment like anything else in the system.
export function CreateContentPage() {
  const [guides, setGuides] = useState<StyleGuide[]>([]);
  const [styleGuideId, setStyleGuideId] = useState("");
  const [text, setText] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("en-US");
  const [targetLanguage, setTargetLanguage] = useState("fr-FR");
  // Phase 16 — which model actually does the translation; "" = app default
  // (settings.translation_provider). See TRANSLATE_PROVIDERS' docstring in
  // api/client.ts for why NMT-only entries (Google Translate, MS
  // Translator) are listed here but not in the Redrive Console's evaluate
  // dropdown.
  const [provider, setProvider] = useState("");
  // Phase 18 — which model WITHIN provider (Ollama/LMStudio/vLLM/Claude/
  // OpenAI/Gemini all offer more than one) — "" = provider's own default.
  const [model, setModel] = useState("");

  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckSourceResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<RetrievePreview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<TranslateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.listStyleGuides().then(setGuides); }, []);

  async function runCheckSource() {
    if (!text.trim()) return;
    setChecking(true);
    setError(null);
    try {
      setCheckResult(await api.checkSource({ text, language: sourceLanguage, style_guide_id: styleGuideId || undefined }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  }

  async function runRetrievePreview() {
    if (!text.trim()) return;
    setPreviewing(true);
    setError(null);
    try {
      setPreview(await api.retrievePreview({
        text, source_language: sourceLanguage, target_language: targetLanguage, style_guide_id: styleGuideId || undefined,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewing(false);
    }
  }

  async function submitTranslation() {
    if (!text.trim()) return;
    setSubmitting(true);
    setError(null);
    setSubmitted(null);
    try {
      setSubmitted(await api.createTranslation({
        source_text: text, source_language: sourceLanguage, target_language: targetLanguage,
        method: "ai", context: "website", style_guide_id: styleGuideId || undefined,
        provider: provider || undefined, model: model || undefined,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 760 }}>
      <PageIntro
        title="Create Content"
        requires="type or paste source copy in the box below. Checking voice/tone and previewing retrieval context are optional — Translate is the only required step."
      >
        Write new copy, check it against brand voice before translation, see what context the AI
        translation would use, then submit it for translation with full provenance.
      </PageIntro>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
        <label style={{ fontSize: 13 }}>
          Style guide
          <select value={styleGuideId} onChange={(e) => setStyleGuideId(e.target.value)}
                  style={{ display: "block", padding: 4, marginTop: 4, minWidth: 200 }}>
            <option value="">None / all guides</option>
            {guides.map((g) => <option key={g.id} value={g.id}>{g.name} v{g.version}</option>)}
          </select>
        </label>
        <LocaleSelect value={sourceLanguage} onChange={setSourceLanguage} label="Source language" width={130} />
        <LocaleSelect value={targetLanguage} onChange={setTargetLanguage} label="Target language" width={130} />
        <ModelPicker
          providers={TRANSLATE_PROVIDERS} provider={provider} model={model}
          onProviderChange={setProvider} onModelChange={setModel} label="Translate with"
        />
      </div>

      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={5} placeholder="Write or paste your copy here…"
        style={{ width: "100%", padding: 10, fontSize: 14, boxSizing: "border-box", marginBottom: 10 }}
      />

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <button disabled={checking || !text.trim()} onClick={runCheckSource} style={{ padding: "6px 14px", cursor: "pointer" }}>
          {checking ? "Checking…" : "Check voice/tone"}
        </button>
        <button disabled={previewing || !text.trim()} onClick={runRetrievePreview} style={{ padding: "6px 14px", cursor: "pointer" }}>
          {previewing ? "Loading…" : "Preview retrieval context"}
        </button>
        <button disabled={submitting || !text.trim()} onClick={submitTranslation} style={{ padding: "6px 14px", cursor: "pointer", fontWeight: 600 }}>
          {submitting ? "Submitting…" : "Translate →"}
        </button>
      </div>

      {checkResult && (
        <div style={{ marginBottom: 16, padding: 12, background: checkResult.needs_review ? "#fffbeb" : "#f0fdf4", borderRadius: 6, fontSize: 13 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Voice check</div>
          {checkResult.needs_review ? (
            <div style={{ color: "#92400e" }}>Couldn't score automatically — {checkResult.reasons.join(", ")}</div>
          ) : (
            <div style={{ display: "flex", gap: 16 }}>
              <span>Tone: <strong>{checkResult.tone_score ?? "—"}</strong></span>
              <span>Voice: <strong>{checkResult.voice_score ?? "—"}</strong></span>
              <span>Overall: <strong>{checkResult.overall_score ?? "—"}</strong></span>
            </div>
          )}
          {checkResult.reasons.length > 0 && !checkResult.needs_review && (
            <div style={{ color: "#6b7280", marginTop: 4 }}>{checkResult.reasons.join(" ")}</div>
          )}
        </div>
      )}

      {preview && (
        <div style={{ marginBottom: 16, padding: 12, background: "#f9fafb", borderRadius: 6, fontSize: 13 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>What the AI would use</div>
          {preview.rules.length === 0 && preview.terms.length === 0 && preview.exemplars.length === 0 ? (
            <div style={{ color: "#9ca3af" }}>No matching style rules, glossary terms, or prior translations found.</div>
          ) : (
            <>
              {preview.rules.map((f) => <div key={f.id}>📐 {f.text}</div>)}
              {preview.terms.map((f) => <div key={f.id}>🔤 {f.text}</div>)}
              {preview.exemplars.map((f) => <div key={f.id}>💬 {f.text}</div>)}
            </>
          )}
        </div>
      )}

      {submitted && (
        <div style={{ padding: 12, background: "#f0fdf4", borderRadius: 6, border: "1px solid #bbf7d0", fontSize: 13 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Translated</div>
          <div style={{ marginBottom: 8 }}>{submitted.translated_text}</div>
          <div style={{ color: "#6b7280" }}>
            Unit id: <code>{submitted.translation_unit_id}</code> — head to Quality Review → Review to see it in context,
            or Redrive to score/improve it.
          </div>
        </div>
      )}
    </div>
  );
}
