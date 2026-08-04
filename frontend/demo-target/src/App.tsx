import { useEffect, useState } from "react";
import { initReviewOverlay } from "../../review-sdk/overlay";

// 8001, not 8000 — this machine also runs another project's stack on
// 8000/5432/6379/3000/9090; see docker-compose.yml's port comment.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8001/api/v1";

interface TranslationUnit {
  id: string;
  source_text: string;
  target_text: string | null;
  target_language: string;
}

// Seed content this demo renders on first load if the target locale has
// nothing yet — a real target app already has its own content; this fixture
// exists purely so Phase 5's overlay has something real to point at without
// depending on same-day cooperation from another repo (peripateticware is a
// later test case, not this).
const SEED_CONTENT = [
  "Welcome to our platform.",
  "We help teams translate content with full provenance tracking.",
  "Get started",
  "All translations are tracked from source to deployment.",
];

function useLocale(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("locale") ?? "fr-FR";
}

// Finds (or creates) exactly this demo's SEED_CONTENT units, matched by
// exact source_text — NOT "take whatever the list endpoint returns first".
// The API has no notion of a demo-owned namespace, and after enough manual
// testing + pytest runs the DB accumulates plenty of other fr-FR content
// (e.g. pytest's "Deployment test."), so positional "first 4 results" is
// unreliable — it was previously showing unrelated test fixture text.
async function ensureSeeded(locale: string): Promise<TranslationUnit[]> {
  const res = await fetch(`${API_BASE}/translations/?target_language=${encodeURIComponent(locale)}&limit=500`);
  const existing: TranslationUnit[] = res.ok ? await res.json() : [];
  const bySourceText = new Map(existing.map((u) => [u.source_text, u]));

  const result: TranslationUnit[] = [];
  for (const source_text of SEED_CONTENT) {
    const found = bySourceText.get(source_text);
    if (found) {
      result.push(found);
      continue;
    }
    const createRes = await fetch(`${API_BASE}/translations/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_text, source_language: "en-US", target_language: locale,
        method: "ai", context: "website",
      }),
    });
    const created = await createRes.json();
    result.push({
      id: created.translation_unit_id,
      source_text,
      target_text: created.translated_text,
      target_language: locale,
    });
  }
  return result;
}

export default function App() {
  const locale = useLocale();
  const [units, setUnits] = useState<TranslationUnit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await ensureSeeded(locale);
        if (!cancelled) setUnits(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; };
  }, [locale]);

  useEffect(() => {
    if (units && units.length > 0) {
      initReviewOverlay({ apiBase: API_BASE });
    }
  }, [units]);

  if (error) {
    return (
      <div style={{ fontFamily: "sans-serif", padding: "2rem", color: "#b91c1c" }}>
        <h1>Demo target couldn't reach the content-provenance API</h1>
        <p>{error}</p>
        <p>Expected API at <code>{API_BASE}</code> — is the backend running?</p>
      </div>
    );
  }

  if (!units) {
    return <div style={{ fontFamily: "sans-serif", padding: "2rem" }}>Loading demo content…</div>;
  }

  const [title, body, cta, footnote] = units;
  const fontStack = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

  return (
    <div style={{ fontFamily: fontStack, color: "#1f2937", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Nav — static site chrome, not part of the reviewable translation content */}
      <nav style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "1rem 2rem", borderBottom: "1px solid #eef0f2", position: "sticky", top: 0,
        background: "rgba(255,255,255,0.9)", backdropFilter: "blur(6px)", zIndex: 10,
      }}>
        <div style={{ fontWeight: 800, fontSize: "1.15rem", letterSpacing: "-0.02em" }}>Acme</div>
        <div style={{ display: "flex", gap: "1.75rem", fontSize: "0.9rem", color: "#4b5563" }}>
          <span>Product</span><span>Pricing</span><span>About</span><span>Contact</span>
        </div>
        <div style={{ fontSize: "0.75rem", color: "#9ca3af" }}>
          locale: <strong>{locale}</strong>
        </div>
      </nav>

      {/* Hero */}
      <section style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        background: "linear-gradient(180deg, #f8fafc 0%, #ffffff 60%)", padding: "5rem 1.5rem",
      }}>
        <div style={{ maxWidth: 640, textAlign: "center" }}>
          {title && (
            <h1 data-tu-id={title.id} style={{
              fontSize: "2.75rem", fontWeight: 800, letterSpacing: "-0.03em",
              lineHeight: 1.15, marginBottom: "1.25rem", color: "#0f172a",
            }}>
              {title.target_text}
            </h1>
          )}
          {body && (
            <p data-tu-id={body.id} style={{ fontSize: "1.2rem", lineHeight: 1.6, color: "#4b5563", marginBottom: "2rem" }}>
              {body.target_text}
            </p>
          )}
          {cta && (
            <button
              data-tu-id={cta.id}
              style={{
                padding: "0.85rem 2rem", fontSize: "1rem", fontWeight: 600,
                background: "#111827", color: "white", border: "none", borderRadius: "8px",
                cursor: "pointer", boxShadow: "0 1px 2px rgba(0,0,0,0.05), 0 4px 12px rgba(17,24,39,0.15)",
              }}
            >
              {cta.target_text}
            </button>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer style={{
        borderTop: "1px solid #eef0f2", padding: "1.5rem 2rem",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        {footnote && (
          <p data-tu-id={footnote.id} style={{ fontSize: "0.85rem", color: "#6b7280", margin: 0 }}>
            {footnote.target_text}
          </p>
        )}
        <span style={{ fontSize: "0.75rem", color: "#9ca3af" }}>© Acme — review demo fixture</span>
      </footer>
    </div>
  );
}
