import { useEffect, useState } from "react";
import { api, imageFileUrl, type ImageAsset } from "../api/client";

// Phase 17 — POST /images/{id}/context-link and GET /images/context-links/
// {unit_id} existed with zero UI: ImageReview.tsx only ever uploads
// kind="translatable" (standalone banners), so there was no path at all
// to attach a reference screenshot to a text segment, despite the review
// overlay/README both describing that as a real capability.
export function ContextImages({ unitId }: { unitId: string }) {
  const [images, setImages] = useState<ImageAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api.getContextImages(unitId).then(setImages).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => { setImages([]); setError(null); refresh(); }, [unitId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      const asset = await api.uploadImage(file, "context");
      await api.linkImageAsContext(asset.id, unitId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div style={{ fontSize: 12, color: "#6b7280" }}>
      <div style={{ fontWeight: 600, color: "#111827", marginBottom: 4 }}>Context screenshots</div>
      {error && <div style={{ color: "#b91c1c", marginBottom: 6 }}>{error}</div>}
      {images.length === 0 ? (
        <div style={{ marginBottom: 6 }}>None attached — a screenshot here helps a reviewer see the segment in its real layout.</div>
      ) : (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          {images.map((img) => (
            <img key={img.id} src={imageFileUrl(img.id)} alt={img.alt_text ?? ""}
                 style={{ maxWidth: 140, maxHeight: 100, borderRadius: 6, border: "1px solid #e5e7eb" }} />
          ))}
        </div>
      )}
      <input type="file" accept="image/*" disabled={busy} onChange={handleUpload} />
    </div>
  );
}
