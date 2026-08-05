import { useState } from "react";
import { api, auditPdfUrl, type SiteAuditFinding } from "../api/client";

// Public-facing lead-gen landing for the site audit tool, styled to match
// thewordinbits.com's own theme (colors/fonts pulled directly from the
// live site: Elementor global colors #3F6355/#B98B4E/#1C2B39/#FAF8F3,
// Fraunces for headings, IBM Plex Sans for body) rather than the internal
// tool's plain system-ui look — a visitor arriving from thewordinbits.com
// shouldn't feel like they've landed on a different, unbranded product.
// This is the ONLY thing served at the public subdomain (see App.tsx's
// VITE_PUBLIC_SITE branch) — the rest of the internal review/redrive/etc.
// tooling isn't meant for public visitors.

const COLORS = {
  cream: "#FAF8F3",
  parchment: "#F1ECDD",
  text: "#1C2B39",
  nearBlack: "#15202B",
  primary: "#3F6355",
  secondary: "#B98B4E",
  stone: "#D8D2C4",
};

const heading: React.CSSProperties = {
  fontFamily: "Fraunces, serif", fontWeight: 600, color: COLORS.nearBlack, margin: 0,
};
const body: React.CSSProperties = {
  fontFamily: '"IBM Plex Sans", sans-serif', color: COLORS.text, lineHeight: 1.6,
};

type Stage = "form" | "running" | "results" | "error";

const CHECK_BLURBS: { title: string; body: string }[] = [
  {
    title: "Mixed-Locale Content",
    body: "We check every page against the language it's supposed to be in — flagging pages, links, and embeds that quietly slipped back to English.",
  },
  {
    title: "Privacy & Regulatory Compliance",
    body: "We map your site against GDPR, CCPA, LGPD, and other regimes by region — cookie consent, opt-out links, and whether your policy even mentions the right law.",
  },
  {
    title: "Technical Readiness",
    body: "RTL/logical-CSS support, font coverage for non-Latin scripts, hreflang correctness, and hardcoded US-only assumptions in your forms and formatting.",
  },
  {
    title: "Localization Completeness",
    body: "For sites already live in multiple languages: translation coverage gaps, language switchers that lose your place, untranslated SEO metadata, and checkout pages still priced and processed as US-only.",
  },
];

export function PublicAuditLanding() {
  const [stage, setStage] = useState<Stage>("form");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState("");
  const [primaryLanguage, setPrimaryLanguage] = useState("en");
  const [error, setError] = useState<string | null>(null);
  const [auditId, setAuditId] = useState<string | null>(null);
  const [findings, setFindings] = useState<SiteAuditFinding[] | null>(null);
  const [pagesCrawled, setPagesCrawled] = useState(0);

  const emailValid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
  const canSubmit = url.trim().length > 3 && emailValid;

  async function runAudit() {
    if (!canSubmit) return;
    setStage("running");
    setError(null);
    try {
      const audit = await api.createAuditRun({
        root_url: url.trim(), primary_language: primaryLanguage, requester_email: email.trim(),
        max_pages: 20,
      });
      if (audit.status === "failed") {
        setError(audit.error || "We couldn't reach that site — double-check the URL and try again.");
        setStage("error");
        return;
      }
      setAuditId(audit.id);
      setPagesCrawled(audit.pages_crawled);
      const findingsList = await api.getAuditFindings(audit.id);
      setFindings(findingsList);
      setStage("results");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStage("error");
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: COLORS.cream, fontFamily: '"IBM Plex Sans", sans-serif' }}>
      <header style={{
        display: "flex", alignItems: "center", gap: 16, padding: "28px 32px",
        borderBottom: `1px solid ${COLORS.stone}`,
      }}>
        <img src="/wordinbits-logo.png" alt="Word in Bits" style={{ width: 44, height: 44 }} />
        <div>
          <div style={{ ...heading, fontSize: 22 }}>The Word in Bits</div>
          <div style={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: 12, color: COLORS.primary, fontStyle: "italic" }}>
            Trusted content for every market
          </div>
        </div>
        <a
          href="https://thewordinbits.com" style={{ marginLeft: "auto", fontSize: 13, color: COLORS.text, textDecoration: "underline" }}
        >
          ← thewordinbits.com
        </a>
      </header>

      <main style={{ maxWidth: 760, margin: "0 auto", padding: "56px 24px 80px" }}>
        {stage === "form" && (
          <>
            <h1 style={{ ...heading, fontSize: 42, lineHeight: 1.25, marginBottom: 20 }}>
              How prepared is your site to enter new markets?
            </h1>
            <p style={{ ...body, fontSize: 17, marginBottom: 40 }}>
              Every engagement starts with an honest picture of where you are. Run our free automated
              readiness check against your live site and get a report in minutes — no obligation, no sales call to book first.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 20, marginBottom: 48 }}>
              {CHECK_BLURBS.map((c) => (
                <div key={c.title}>
                  <h3 style={{ ...heading, fontSize: 20, color: COLORS.primary, marginBottom: 4 }}>{c.title}</h3>
                  <p style={{ ...body, fontSize: 15 }}>{c.body}</p>
                </div>
              ))}
            </div>

            <div style={{
              background: COLORS.parchment, border: `1px solid ${COLORS.stone}`, borderRadius: 4,
              padding: 28,
            }}>
              <h2 style={{ ...heading, fontSize: 22, marginBottom: 16 }}>Get your free report</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <label style={{ fontSize: 13, ...body }}>
                  Website URL
                  <input
                    value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yoursite.com"
                    style={{
                      display: "block", width: "100%", marginTop: 6, padding: 10, boxSizing: "border-box",
                      border: `1px solid ${COLORS.stone}`, borderRadius: 3, fontFamily: '"IBM Plex Sans", sans-serif', fontSize: 15,
                    }}
                  />
                </label>
                <label style={{ fontSize: 13, ...body }}>
                  Your email <span style={{ color: "#8a8477" }}>(so we can follow up with what we find)</span>
                  <input
                    type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com"
                    style={{
                      display: "block", width: "100%", marginTop: 6, padding: 10, boxSizing: "border-box",
                      border: `1px solid ${email && !emailValid ? "#c0392b" : COLORS.stone}`, borderRadius: 3,
                      fontFamily: '"IBM Plex Sans", sans-serif', fontSize: 15,
                    }}
                  />
                </label>
                <label style={{ fontSize: 13, ...body }}>
                  Language you currently publish in
                  <input
                    value={primaryLanguage} onChange={(e) => setPrimaryLanguage(e.target.value)}
                    style={{
                      display: "block", width: 120, marginTop: 6, padding: 10, boxSizing: "border-box",
                      border: `1px solid ${COLORS.stone}`, borderRadius: 3, fontFamily: '"IBM Plex Sans", sans-serif', fontSize: 15,
                    }}
                  />
                </label>
                <button
                  onClick={runAudit} disabled={!canSubmit}
                  style={{
                    marginTop: 8, padding: "12px 0", border: "none", borderRadius: 3, cursor: canSubmit ? "pointer" : "default",
                    background: canSubmit ? COLORS.primary : COLORS.stone, color: "white",
                    fontFamily: '"IBM Plex Sans", sans-serif', fontWeight: 600, fontSize: 15,
                  }}
                >
                  Check my site's readiness
                </button>
              </div>
            </div>
          </>
        )}

        {stage === "running" && (
          <div style={{ textAlign: "center", padding: "80px 0" }}>
            <h2 style={{ ...heading, fontSize: 26, marginBottom: 12 }}>Analyzing {url}…</h2>
            <p style={{ ...body, color: "#6b7280" }}>
              This usually takes one to three minutes — we're crawling your site and checking it
              against ten different readiness signals.
            </p>
          </div>
        )}

        {stage === "error" && (
          <div style={{ textAlign: "center", padding: "80px 0" }}>
            <h2 style={{ ...heading, fontSize: 26, marginBottom: 12, color: "#c0392b" }}>Something went wrong</h2>
            <p style={{ ...body, marginBottom: 24 }}>{error}</p>
            <button
              onClick={() => setStage("form")}
              style={{
                padding: "10px 24px", border: `1px solid ${COLORS.primary}`, borderRadius: 3, cursor: "pointer",
                background: "transparent", color: COLORS.primary, fontFamily: '"IBM Plex Sans", sans-serif', fontWeight: 600,
              }}
            >
              Try again
            </button>
          </div>
        )}

        {stage === "results" && findings && auditId && (
          <ResultsView url={url} auditId={auditId} findings={findings} pagesCrawled={pagesCrawled} colors={COLORS} headingStyle={heading} bodyStyle={body} />
        )}
      </main>

      <footer style={{ textAlign: "center", padding: "24px", color: "#8a8477", fontSize: 12, ...body }}>
        © {new Date().getFullYear()} The Word in Bits — <a href="https://thewordinbits.com" style={{ color: COLORS.primary }}>thewordinbits.com</a>
      </footer>
    </div>
  );
}

function ResultsView({
  url, auditId, findings, pagesCrawled, colors, headingStyle, bodyStyle,
}: {
  url: string; auditId: string; findings: SiteAuditFinding[]; pagesCrawled: number;
  colors: typeof COLORS; headingStyle: React.CSSProperties; bodyStyle: React.CSSProperties;
}) {
  const bySeverity = { critical: 0, warning: 0, info: 0 } as Record<string, number>;
  for (const f of findings) bySeverity[f.severity] = (bySeverity[f.severity] ?? 0) + 1;
  const topFindings = [...findings]
    .sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "critical" ? -1 : b.severity === "critical" ? 1 : 0))
    .slice(0, 4);
  const severityColor: Record<string, string> = { critical: "#c0392b", warning: colors.secondary, info: colors.primary };

  return (
    <div>
      <h1 style={{ ...headingStyle, fontSize: 32, marginBottom: 8 }}>Your readiness report is ready</h1>
      <p style={{ ...bodyStyle, marginBottom: 32 }}>
        We checked {pagesCrawled} page{pagesCrawled === 1 ? "" : "s"} of {url} and found {findings.length} thing{findings.length === 1 ? "" : "s"} worth knowing about.
      </p>

      <div style={{ display: "flex", gap: 16, marginBottom: 40 }}>
        {(["critical", "warning", "info"] as const).map((sev) => (
          <div key={sev} style={{
            flex: 1, background: colors.parchment, border: `1px solid ${colors.stone}`, borderRadius: 4,
            padding: 16, textAlign: "center",
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: severityColor[sev], fontFamily: "Fraunces, serif" }}>
              {bySeverity[sev] ?? 0}
            </div>
            <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: colors.text }}>{sev}</div>
          </div>
        ))}
      </div>

      {topFindings.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          <h2 style={{ ...headingStyle, fontSize: 20, marginBottom: 12 }}>A few things we noticed</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {topFindings.map((f) => (
              <div key={f.id} style={{
                padding: 12, borderLeft: `3px solid ${severityColor[f.severity]}`, background: colors.parchment,
                fontSize: 14, ...bodyStyle,
              }}>
                {f.summary}
              </div>
            ))}
          </div>
          {findings.length > topFindings.length && (
            <p style={{ ...bodyStyle, fontSize: 13, color: "#8a8477", marginTop: 8 }}>
              + {findings.length - topFindings.length} more in your full report.
            </p>
          )}
        </div>
      )}

      <a
        href={auditPdfUrl(auditId)} download
        style={{
          display: "inline-block", padding: "14px 32px", background: colors.primary, color: "white",
          textDecoration: "none", borderRadius: 3, fontWeight: 600, fontFamily: '"IBM Plex Sans", sans-serif',
        }}
      >
        Download your full PDF report
      </a>

      <p style={{ ...bodyStyle, marginTop: 24, fontSize: 14, color: "#8a8477" }}>
        We'll follow up by email with a walkthrough of what we found and where to start.
      </p>
    </div>
  );
}
