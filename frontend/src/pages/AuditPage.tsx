import { useEffect, useState } from "react";
import { api, type SiteAudit, type SiteAuditCheck } from "../api/client";
import { AuditReport } from "../components/AuditReport";

interface Props {
  onReviewPage?: (url: string, locale: string) => void;
}

const ALL_CHECKS: { id: SiteAuditCheck; label: string }[] = [
  { id: "mixed_locale", label: "Mixed locale" },
  { id: "rtl_readiness", label: "RTL / logical CSS" },
  { id: "icu_i18n", label: "ICU / i18n tooling" },
  { id: "privacy", label: "Privacy & regulatory" },
  { id: "text_expansion", label: "Text expansion risk" },
  { id: "font_coverage", label: "Font / script coverage" },
  { id: "hreflang", label: "hreflang / SEO" },
  { id: "cookie_consent", label: "Cookie consent" },
  { id: "placeholder_leak", label: "Placeholder leakage" },
  { id: "locale_format", label: "Locale format assumptions" },
];

// Phase 11 — crawls a third-party site (not this system's own translations)
// looking for i18n/l10n/compliance issues: mixed locales, RTL/logical-CSS
// readiness, ICU/i18n-tooling usage, and privacy-policy language mismatches.
// Replaces three standalone scripts the user previously ran by hand.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function AuditPage({ onReviewPage }: Props) {
  const [rootUrl, setRootUrl] = useState("");
  const [requesterEmail, setRequesterEmail] = useState("");
  const [primaryLanguage, setPrimaryLanguage] = useState("en");
  const [maxPages, setMaxPages] = useState(40);
  const [checks, setChecks] = useState<Set<SiteAuditCheck>>(new Set(ALL_CHECKS.map((c) => c.id)));
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [runs, setRuns] = useState<SiteAudit[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  function reloadRuns() {
    api.listAuditRuns().then(setRuns).catch(() => setRuns([]));
  }

  useEffect(() => { reloadRuns(); }, []);

  function toggleCheck(id: SiteAuditCheck) {
    setChecks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  const emailValid = EMAIL_RE.test(requesterEmail.trim());

  async function startAudit() {
    if (!rootUrl.trim() || !emailValid) return;
    setRunning(true);
    setError(null);
    try {
      const audit = await api.createAuditRun({
        root_url: rootUrl, primary_language: primaryLanguage, requester_email: requesterEmail.trim(),
        max_pages: maxPages, checks: Array.from(checks),
      });
      reloadRuns();
      setSelectedId(audit.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 960, display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <h2 style={{ marginTop: 0 }}>Site Audit</h2>
        <p style={{ color: "#6b7280", fontSize: 13 }}>
          Crawl a website (not this system's own translations) to find mixed-locale content, pages at risk of
          poor RTL support, ICU/i18n tooling in use, and privacy-policy language mismatches.
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 480 }}>
        <label style={{ fontSize: 13 }}>
          Root URL
          <input
            value={rootUrl} onChange={(e) => setRootUrl(e.target.value)}
            placeholder="https://example.com"
            style={{ display: "block", width: "100%", marginTop: 4, padding: 4, boxSizing: "border-box" }}
          />
        </label>
        <label style={{ fontSize: 13 }}>
          Your email <span style={{ color: "#9ca3af" }}>(so we can send you this report)</span>
          <input
            type="email" value={requesterEmail} onChange={(e) => setRequesterEmail(e.target.value)}
            placeholder="you@example.com"
            style={{
              display: "block", width: "100%", marginTop: 4, padding: 4, boxSizing: "border-box",
              borderColor: requesterEmail && !emailValid ? "#e5484d" : undefined,
            }}
          />
        </label>
        <label style={{ fontSize: 13 }}>
          Primary language
          <input
            value={primaryLanguage} onChange={(e) => setPrimaryLanguage(e.target.value)}
            style={{ display: "block", width: 100, marginTop: 4, padding: 4 }}
          />
        </label>
        <label style={{ fontSize: 13 }}>
          Max pages
          <input
            type="number" min={1} max={200} value={maxPages}
            onChange={(e) => setMaxPages(Number(e.target.value))}
            style={{ display: "block", width: 100, marginTop: 4, padding: 4 }}
          />
        </label>
        <div>
          <div style={{ fontSize: 13, marginBottom: 4 }}>Checks</div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {ALL_CHECKS.map((c) => (
              <label key={c.id} style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}>
                <input type="checkbox" checked={checks.has(c.id)} onChange={() => toggleCheck(c.id)} />
                {c.label}
              </label>
            ))}
          </div>
        </div>
        <button onClick={startAudit} disabled={running || !rootUrl.trim() || !emailValid} style={{ padding: "6px 0", cursor: "pointer" }}>
          {running ? "Crawling… (this can take a while)" : "Start audit"}
        </button>
        {error && (
          <div style={{ fontSize: 12, color: "#b91c1c", background: "#fef2f2", padding: 8, borderRadius: 6 }}>
            {error}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 24 }}>
        <div style={{ width: 260, flexShrink: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Past audits</div>
          {runs === null && <div style={{ fontSize: 12, color: "#9ca3af" }}>Loading…</div>}
          {runs?.length === 0 && <div style={{ fontSize: 12, color: "#9ca3af" }}>No audits yet.</div>}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {runs?.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelectedId(r.id)}
                style={{
                  textAlign: "left", fontSize: 12, padding: 6, cursor: "pointer", borderRadius: 4,
                  border: "1px solid #e5e7eb", background: r.id === selectedId ? "#f3f4f6" : "white",
                }}
              >
                <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.root_url}
                </div>
                <div style={{ color: "#6b7280" }}>{r.status} · {new Date(r.started_at).toLocaleString()}</div>
                {r.requester_email && (
                  <div style={{ color: "#9ca3af", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.requester_email}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {selectedId ? (
            <AuditReport auditId={selectedId} onReviewPage={onReviewPage} />
          ) : (
            <div style={{ color: "#9ca3af", fontSize: 13 }}>Select an audit to see its findings.</div>
          )}
        </div>
      </div>
    </div>
  );
}
