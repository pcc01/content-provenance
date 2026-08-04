import { useState } from "react";
import { api, imageFileUrl, type ImageAsset, type ImageTranslationUnit } from "../api/client";

// Standalone translatable image assets (banners etc.) — NOT embedded in a
// live page, so they don't get an in-context overlay box the way text
// segments do. Context images (screenshots linked to a text segment) need
// no separate panel here — they render in-page and get their own highlight
// box like any other segment (see ReviewPage/SegmentDrawer).
export function ImageReview() {
  const [sourceImage, setSourceImage] = useState<ImageAsset | null>(null);
  const [itu, setItu] = useState<ImageTranslationUnit | null>(null);
  const [targetImage, setTargetImage] = useState<ImageAsset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [sourceLanguage, setSourceLanguage] = useState("en-US");
  const [targetLanguage, setTargetLanguage] = useState("fr-FR");
  const [method, setMethod] = useState("human");
  const [translatorName, setTranslatorName] = useState("");

  const [lookupId, setLookupId] = useState("");

  async function handleUploadSource(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      const asset = await api.uploadImage(file, "translatable");
      setSourceImage(asset);
      setItu(null);
      setTargetImage(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleLocalize(targetFile?: File) {
    if (!sourceImage) return;
    setError(null);
    setBusy(true);
    try {
      const result = await api.localizeImage(
        sourceImage.id,
        { source_language: sourceLanguage, target_language: targetLanguage, method, translator_name: translatorName || undefined },
        targetFile,
      );
      setItu(result);
      if (result.target_image_id) {
        setTargetImage(await api.getImage(result.target_image_id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAttachTarget(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !itu) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await api.attachLocalizedImage(itu.id, file);
      setItu(updated);
      if (updated.target_image_id) {
        setTargetImage(await api.getImage(updated.target_image_id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleLookup() {
    if (!lookupId.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const found = await api.getImageTranslationUnit(lookupId.trim());
      setItu(found);
      setSourceImage(await api.getImage(found.source_image_id));
      setTargetImage(found.target_image_id ? await api.getImage(found.target_image_id) : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 800 }}>
      <h2 style={{ marginTop: 0 }}>Image Review</h2>
      <p style={{ color: "#6b7280" }}>
        Standalone translatable images (banners, graphics) — upload a source image, localize it,
        and review both versions with their provenance. Context screenshots linked to a text
        segment appear inline in the Review tab instead.
      </p>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 24 }}>
        <input value={lookupId} onChange={(e) => setLookupId(e.target.value)} placeholder="Look up an existing image translation unit by id…" style={{ flex: 1, padding: 6, fontSize: 13 }} />
        <button onClick={handleLookup} disabled={busy} style={{ padding: "6px 14px", cursor: "pointer" }}>Look up</button>
      </div>

      <section style={{ marginBottom: 24 }}>
        <h3>1. Upload a source image</h3>
        <input type="file" accept="image/*" onChange={handleUploadSource} disabled={busy} />
        {sourceImage && (
          <div style={{ marginTop: 8 }}>
            <img src={imageFileUrl(sourceImage.id)} alt="" style={{ maxWidth: 300, borderRadius: 6, border: "1px solid #e5e7eb" }} />
            <div style={{ fontSize: 12, color: "#6b7280" }}>{sourceImage.id}</div>
          </div>
        )}
      </section>

      {sourceImage && (
        <section style={{ marginBottom: 24 }}>
          <h3>2. Localize</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 320 }}>
            <label style={{ fontSize: 13 }}>
              Source language
              <input value={sourceLanguage} onChange={(e) => setSourceLanguage(e.target.value)} style={{ display: "block", width: "100%", padding: 4 }} />
            </label>
            <label style={{ fontSize: 13 }}>
              Target language
              <input value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)} style={{ display: "block", width: "100%", padding: 4 }} />
            </label>
            <label style={{ fontSize: 13 }}>
              Method
              <select value={method} onChange={(e) => setMethod(e.target.value)} style={{ display: "block", width: "100%", padding: 4 }}>
                <option value="human">human</option>
                <option value="ai">ai</option>
                <option value="hybrid">hybrid</option>
              </select>
            </label>
            <label style={{ fontSize: 13 }}>
              Translator name (optional)
              <input value={translatorName} onChange={(e) => setTranslatorName(e.target.value)} style={{ display: "block", width: "100%", padding: 4 }} />
            </label>
            <label style={{ fontSize: 13 }}>
              Localized image (optional — leave blank to start pending, attach later)
              <input
                type="file" accept="image/*" disabled={busy}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleLocalize(f); }}
              />
            </label>
            {!itu && (
              <button onClick={() => handleLocalize()} disabled={busy} style={{ padding: "6px 14px", cursor: "pointer" }}>
                Start localization (no target image yet)
              </button>
            )}
          </div>
        </section>
      )}

      {itu && (
        <section>
          <h3>Result</h3>
          <div style={{ fontSize: 13, marginBottom: 8 }}>
            Status: <strong>{itu.status}</strong> · {itu.source_language} → {itu.target_language} · method: {itu.translation_method}
          </div>
          <div style={{ display: "flex", gap: 16 }}>
            <div>
              <div style={{ fontSize: 12, color: "#6b7280" }}>Source</div>
              {sourceImage && <img src={imageFileUrl(sourceImage.id)} alt="" style={{ maxWidth: 280, borderRadius: 6, border: "1px solid #e5e7eb" }} />}
            </div>
            <div>
              <div style={{ fontSize: 12, color: "#6b7280" }}>Target</div>
              {targetImage ? (
                <img src={imageFileUrl(targetImage.id)} alt="" style={{ maxWidth: 280, borderRadius: 6, border: "1px solid #e5e7eb" }} />
              ) : (
                <div style={{ width: 280 }}>
                  <p style={{ fontSize: 12, color: "#9ca3af" }}>Not attached yet.</p>
                  <input type="file" accept="image/*" disabled={busy} onChange={handleAttachTarget} />
                </div>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
