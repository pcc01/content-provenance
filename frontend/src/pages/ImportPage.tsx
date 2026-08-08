import { useState } from "react";
import { api } from "../api/client";
import { PageIntro } from "../components/PageIntro";

// Phase 13/9b.1 — bring legacy vendor content into the system: TMX
// (translation memory — becomes retrieval context, not live translation
// units, see app/tm/tmx_import.py's docstring) and XLIFF (becomes live,
// reviewable TranslationUnits, same as any native translation). Both
// already existed as API-only endpoints; this is their first UI surface.
export function ImportPage() {
  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <PageIntro
        title="Import"
        requires="pick the section below that matches your file — TMX for translation memory, XLIFF for a TMS/CAT export — and choose a file. Language/vendor fields are optional context, not required to upload."
      >
        Bring in content from an existing vendor or TMS before creating anything new — TMX seeds
        retrieval context from prior-approved translations, XLIFF brings in live, reviewable units.
      </PageIntro>
      <TmxImport />
      <div style={{ height: 1, background: "#e5e7eb", margin: "28px 0" }} />
      <XliffImport />
    </div>
  );
}

function TmxImport() {
  const [sourceLanguage, setSourceLanguage] = useState("en-US");
  const [targetLanguage, setTargetLanguage] = useState("fr-FR");
  const [sourceSystem, setSourceSystem] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ imported_count: number } | null>(null);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null); setResult(null); setBusy(true);
    try {
      setResult(await api.importTmx(file, {
        source_language: sourceLanguage, target_language: targetLanguage, source_system: sourceSystem || "unknown",
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div>
      <h3 style={{ fontSize: 15 }}>Translation memory (TMX)</h3>
      <p style={{ color: "#6b7280", fontSize: 13 }}>
        A vendor's translation memory export — becomes retrieval context (prior-approved
        translations the AI can draw on), tagged with the vendor's identity.
      </p>
      {error && <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 13 }}>{error}</div>}
      {result && <div style={{ background: "#f0fdf4", color: "#166534", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 13 }}>Imported {result.imported_count} translation pair(s).</div>}
      <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
        <input placeholder="Source language" value={sourceLanguage} onChange={(e) => setSourceLanguage(e.target.value)} style={{ padding: 4, fontSize: 13, width: 110 }} />
        <input placeholder="Target language" value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)} style={{ padding: 4, fontSize: 13, width: 110 }} />
        <input placeholder="Vendor / source system name" value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)} style={{ padding: 4, fontSize: 13, width: 220 }} />
      </div>
      <input type="file" accept=".tmx,application/xml,text/xml" disabled={busy} onChange={handleUpload} />
    </div>
  );
}

function XliffImport() {
  const [sourceSystem, setSourceSystem] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ imported_count: number } | null>(null);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null); setResult(null); setBusy(true);
    try {
      setResult(await api.importXliff(file, sourceSystem || "unknown"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div>
      <h3 style={{ fontSize: 15 }}>XLIFF 2.0</h3>
      <p style={{ color: "#6b7280", fontSize: 13 }}>
        A TMS/CAT tool export, or a re-import of this system's own export — creates live,
        reviewable TranslationUnits, synthesizing provenance if none is embedded.
      </p>
      {error && <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 13 }}>{error}</div>}
      {result && <div style={{ background: "#f0fdf4", color: "#166534", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 13 }}>Imported {result.imported_count} unit(s) — review them in Quality Review → Review.</div>}
      <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
        <input placeholder="Source system name" value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)} style={{ padding: 4, fontSize: 13, width: 220 }} />
      </div>
      <input type="file" accept=".xlf,.xliff,application/xliff+xml" disabled={busy} onChange={handleUpload} />
    </div>
  );
}
