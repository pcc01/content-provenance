import { useEffect, useState } from "react";
import { api, auditExportUrl, auditPdfUrl, type AuditRunSummary, type SiteAuditFinding } from "../api/client";

interface Props {
  auditId: string;
  onReviewPage?: (url: string, locale: string) => void;
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: "#e5484d",
  warning: "#f5a524",
  info: "#60a5fa",
};

const CHECK_LABEL: Record<string, string> = {
  mixed_locale: "Mixed Locale",
  rtl_readiness: "RTL / Logical CSS Readiness",
  icu_i18n: "ICU / I18n Tooling",
  privacy: "Privacy & Regulatory Compliance",
  text_expansion: "Text Expansion Risk",
  font_coverage: "Font / Script Coverage",
  hreflang: "hreflang / SEO Localization",
  cookie_consent: "Cookie Consent",
  placeholder_leak: "Untranslated Placeholder Leakage",
  locale_format: "Locale Format Assumptions",
  translation_coverage: "Translation Coverage",
  locale_switcher: "Locale Switcher Integrity",
  seo_metadata: "SEO Metadata Parity",
  payment_localization: "Payment Localization",
};

function findingUrl(f: SiteAuditFinding): string | null {
  const d = f.detail;
  return (d.url as string) || (d.from_url as string) || (d.privacy_url as string) || (d.embed_url as string) || null;
}

// "Whose code is this?" — text_expansion/rtl_readiness/font_coverage
// attribute each finding to its actual source (see
// app/core/audit/source_attribution.py): a WordPress theme/plugin by
// name when detectable, else a generic same-origin/third-party/inline
// category. Shows the top-ranked source only — the full breakdown is in
// the raw finding detail for anyone who needs it.
function topSource(f: SiteAuditFinding): string | null {
  const list = (f.detail.sources ?? f.detail.font_declaration_sources) as
    { url: string; category: string; platform_detail?: string }[] | undefined;
  if (!list || list.length === 0) return null;
  const top = list[0];
  if (top.platform_detail) return top.platform_detail;
  if (top.category === "inline") return "inline styles on this page";
  if (top.category === "third_party") return `third-party: ${new URL(top.url).hostname}`;
  return top.url;
}

export function AuditReport({ auditId, onReviewPage }: Props) {
  const [summary, setSummary] = useState<AuditRunSummary | null>(null);
  const [findings, setFindings] = useState<SiteAuditFinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSummary(null);
    setFindings(null);
    setError(null);
    Promise.all([api.getAuditRun(auditId), api.getAuditFindings(auditId)])
      .then(([s, f]) => { setSummary(s); setFindings(f); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [auditId]);

  if (error) return <div style={{ color: "#b91c1c", fontSize: 13 }}>{error}</div>;
  if (!summary || !findings) return <div style={{ color: "#9ca3af", fontSize: 13 }}>Loading report…</div>;

  const byCheck: Record<string, SiteAuditFinding[]> = {};
  for (const f of findings) (byCheck[f.check] ??= []).push(f);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong style={{ fontSize: 14 }}>{summary.audit.root_url}</strong>
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            {summary.audit.status} · {summary.audit.pages_crawled} page(s) crawled · {findings.length} finding(s)
            {summary.audit.requester_email && <> · requested by {summary.audit.requester_email}</>}
            {summary.audit.error && <span style={{ color: "#b91c1c" }}> · {summary.audit.error}</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <a href={auditPdfUrl(auditId)} download style={{ fontSize: 12 }}>Download PDF report</a>
          <a href={auditExportUrl(auditId)} download style={{ fontSize: 12 }}>Download report (.txt)</a>
        </div>
      </div>

      {findings.length === 0 && (
        <div style={{ fontSize: 13, color: "#15803d" }}>No issues found.</div>
      )}

      {Object.entries(byCheck).map(([check, items]) => (
        <div key={check}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
            {CHECK_LABEL[check] ?? check} ({items.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {items.map((f) => {
              const url = findingUrl(f);
              const source = topSource(f);
              return (
                <div key={f.id} style={{
                  padding: 8, borderRadius: 6, fontSize: 12,
                  borderLeft: `3px solid ${SEVERITY_COLOR[f.severity]}`, background: "#f9fafb",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span>
                      <strong style={{ textTransform: "uppercase", color: SEVERITY_COLOR[f.severity] }}>
                        {f.severity}
                      </strong>{" "}
                      {f.summary}
                    </span>
                  </div>
                  {source && (
                    <div style={{ marginTop: 4, color: "#6b7280", fontStyle: "italic" }}>Source: {source}</div>
                  )}
                  {url && (
                    <div style={{ marginTop: 4, display: "flex", gap: 8, alignItems: "center" }}>
                      <span style={{ color: "#6b7280", wordBreak: "break-all" }}>{url}</span>
                      {onReviewPage && (
                        <button
                          onClick={() => onReviewPage(url, summary.audit.primary_language)}
                          style={{ fontSize: 11, cursor: "pointer", flexShrink: 0 }}
                        >
                          Review this page
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
