import { useState } from "react";
import { AuditPage } from "./pages/AuditPage";
import { Dashboard } from "./pages/Dashboard";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ImageReview } from "./pages/ImageReview";
import { LiveReviewPage } from "./pages/LiveReviewPage";
import { RedriveConsole } from "./pages/RedriveConsole";
import { ReviewPage } from "./pages/ReviewPage";
import { SearchPage } from "./pages/SearchPage";

type Tab = "review" | "live" | "redrive" | "images" | "documents" | "search" | "dashboard" | "audit";

export default function App() {
  const [tab, setTab] = useState<Tab>("review");
  // Phase 11: lets the Audit tab's "Review this page" button jump straight
  // into fetch-mode review for that URL — a new object on every set() so
  // ReviewPage's effect fires even for a repeat click on the same finding.
  const [reviewTarget, setReviewTarget] = useState<{ url: string; locale: string } | null>(null);

  const tabs: [Tab, string][] = [
    ["review", "Review"],
    ["live", "Live (extension)"],
    ["redrive", "Redrive"],
    ["images", "Images"],
    ["documents", "Documents"],
    ["audit", "Audit"],
    ["search", "Search"],
    ["dashboard", "Dashboard"],
  ];

  function reviewPageFromAudit(url: string, locale: string) {
    setReviewTarget({ url, locale });
    setTab("review");
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", fontFamily: "system-ui, sans-serif" }}>
      <nav style={{
        display: "flex", alignItems: "center", gap: 4, padding: "0 16px",
        borderBottom: "1px solid #e5e7eb", height: 48, flexShrink: 0,
      }}>
        <strong style={{ marginRight: 16, fontSize: 14 }}>Content Provenance</strong>
        {tabs.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              padding: "6px 12px", fontSize: 13, cursor: "pointer", border: "none",
              background: tab === key ? "#f3f4f6" : "transparent",
              borderRadius: 6, fontWeight: tab === key ? 600 : 400,
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      <div style={{ flex: 1, overflow: "hidden" }}>
        {tab === "review" && <ReviewPage initialFetchTarget={reviewTarget} />}
        {tab === "live" && <LiveReviewPage />}
        {tab === "redrive" && <div style={{ overflowY: "auto", height: "100%" }}><RedriveConsole /></div>}
        {tab === "images" && <div style={{ overflowY: "auto", height: "100%" }}><ImageReview /></div>}
        {tab === "documents" && <div style={{ overflowY: "auto", height: "100%" }}><DocumentsPage /></div>}
        {tab === "audit" && <div style={{ overflowY: "auto", height: "100%" }}><AuditPage onReviewPage={reviewPageFromAudit} /></div>}
        {tab === "search" && <div style={{ overflowY: "auto", height: "100%" }}><SearchPage /></div>}
        {tab === "dashboard" && <div style={{ overflowY: "auto", height: "100%" }}><Dashboard /></div>}
      </div>
    </div>
  );
}
