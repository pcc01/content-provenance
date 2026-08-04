import { useEffect, useState } from "react";
import { api, auditExportUrl, type AuditRunSummary, type SiteAuditFinding } from "../api/client";

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
  privacy: "Privacy Policy",
};

function findingUrl(f: SiteAuditFinding): string | null {
  const d = f.detail;
  return (d.url as string) || (d.from_url as string) || (d.privacy_url as string) || (d.embed_url as string) || null;
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
            {summary.audit.error && <span style={{ color: "#b91c1c" }}> · {summary.audit.error}</span>}
          </div>
        </div>
        <a href={auditExportUrl(auditId)} download style={{ fontSize: 12 }}>Download report (.txt)</a>
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
