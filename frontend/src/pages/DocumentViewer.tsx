import { useEffect, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { api, type DocumentMeta, type TranslationUnit } from "../api/client";
import { initReviewOverlay } from "../../review-sdk/overlay";

// The Phase 7a "target page" for a text/Markdown document: this route is
// what gets typed into the Review tab's "target app base URL"/"route"
// fields (base = this Review Shell's own origin, route = /documents/{id}),
// so ReviewFrame iframes it exactly like any external page. Each segment
// renders as a data-tu-id-tagged element and initReviewOverlay() from the
// same SDK demo-target uses takes it from there — no overlay changes needed.
function useLocale(): string {
  return new URLSearchParams(window.location.search).get("locale") ?? "fr-FR";
}

function renderMarkdown(text: string): string {
  const html = marked.parse(text, { async: false }) as string;
  return DOMPurify.sanitize(html);
}

export function DocumentViewer({ documentId }: { documentId: string }) {
  const locale = useLocale();
  const [doc, setDoc] = useState<DocumentMeta | null>(null);
  const [segments, setSegments] = useState<TranslationUnit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await api.getDocumentSegments(documentId, locale);
        if (cancelled) return;
        setDoc(result.document);
        setSegments(result.segments);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; };
  }, [documentId, locale]);

  useEffect(() => {
    if (segments && segments.length > 0) initReviewOverlay();
  }, [segments]);

  if (error) {
    return <div style={{ padding: 24, color: "#b91c1c", fontFamily: "system-ui, sans-serif" }}>{error}</div>;
  }
  if (!doc || !segments) {
    return <div style={{ padding: 24, fontFamily: "system-ui, sans-serif", color: "#6b7280" }}>Loading document…</div>;
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2.5rem 1.5rem", fontFamily: "system-ui, sans-serif", lineHeight: 1.6 }}>
      <h1 style={{ marginBottom: "0.25rem" }}>{doc.title}</h1>
      <p style={{ color: "#9ca3af", fontSize: 13, marginTop: 0, marginBottom: "2rem" }}>
        {doc.source_language} → {locale} · {doc.format}
      </p>
      {segments.length === 0 && (
        <p style={{ color: "#9ca3af" }}>No segments for this document in {locale} yet.</p>
      )}
      {segments.map((seg) =>
        doc.format === "markdown" ? (
          <div
            key={seg.id}
            data-tu-id={seg.id}
            style={{ marginBottom: "1.25rem" }}
            dangerouslySetInnerHTML={{ __html: renderMarkdown(seg.target_text ?? "") }}
          />
        ) : (
          <p key={seg.id} data-tu-id={seg.id} style={{ marginBottom: "1.25rem", whiteSpace: "pre-wrap" }}>
            {seg.target_text}
          </p>
        ),
      )}
    </div>
  );
}
