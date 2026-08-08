import { useState } from "react";
import { AuditPage } from "./pages/AuditPage";
import { ConsistencyPage } from "./pages/ConsistencyPage";
import { CreateContentPage } from "./pages/CreateContentPage";
import { Dashboard } from "./pages/Dashboard";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ImageReview } from "./pages/ImageReview";
import { ImportPage } from "./pages/ImportPage";
import { LiveReviewPage } from "./pages/LiveReviewPage";
import { PublicAuditLanding } from "./pages/PublicAuditLanding";
import { RedriveConsole } from "./pages/RedriveConsole";
import { ReviewPage } from "./pages/ReviewPage";
import { SearchPage } from "./pages/SearchPage";
import { StyleGuidesPage } from "./pages/StyleGuidesPage";
import { VendorScorecardPage } from "./pages/VendorScorecardPage";

// A public-facing deployment (audit.thewordinbits.com) bakes VITE_PUBLIC_SITE
// at build time (see Dockerfile's frontend-build stage) and shows ONLY the
// branded lead-gen audit landing — none of the internal review/redrive/etc.
// tooling is meant for a public visitor. The internal build (this repo's
// own dev/default build) is unaffected — same codebase, one build-time
// switch, not a second app to maintain.
const PUBLIC_SITE = import.meta.env.VITE_PUBLIC_SITE === "true";

export default function App() {
  return PUBLIC_SITE ? <PublicAuditLanding /> : <InternalApp />;
}

// Three segments, matching the actual shape of the work — not an
// arbitrary regroup of the old flat tab bar:
//   Content Creation — bring in or write new copy BEFORE it's translated
//     (style guides define the brand voice everything else checks against,
//     import brings in legacy vendor content, Create is where new copy
//     starts its life). This segment didn't really exist before Phase 13;
//     most of its pages were API-only until this pass.
//   Quality Review — everything about evaluating and improving translated
//     content already in the system: in-context review, redrive,
//     consistency across a whole site, vendor comparison, search.
//   Audit — unchanged: a THIRD-PARTY site compliance tool, a genuinely
//     separate concern from this system's own translated content (see
//     docs/graphrag-provenance-proposal.md's note on why Phase 14's
//     consistency checks did NOT get folded into this same subsystem).
type Segment = "create" | "review" | "audit";
type CreateTab = "create" | "style-guides" | "import" | "documents";
type ReviewTab = "review" | "live" | "redrive" | "images" | "vendors" | "consistency" | "search" | "dashboard";

const SEGMENTS: [Segment, string][] = [
  ["create", "Content Creation"],
  ["review", "Quality Review"],
  ["audit", "Audit"],
];

const CREATE_TABS: [CreateTab, string][] = [
  ["create", "Create"],
  ["style-guides", "Style Guides"],
  ["import", "Import"],
  ["documents", "Documents"],
];

const REVIEW_TABS: [ReviewTab, string][] = [
  ["review", "Review"],
  ["live", "Live (extension)"],
  ["redrive", "Redrive"],
  ["images", "Images"],
  ["vendors", "Vendor Scorecard"],
  ["consistency", "Consistency"],
  ["search", "Search"],
  ["dashboard", "Dashboard"],
];

function InternalApp() {
  const [segment, setSegment] = useState<Segment>("review");
  const [createTab, setCreateTab] = useState<CreateTab>("create");
  const [reviewTab, setReviewTab] = useState<ReviewTab>("review");
  // Phase 11: lets the Audit tab's "Review this page" button jump straight
  // into fetch-mode review for that URL — a new object on every set() so
  // ReviewPage's effect fires even for a repeat click on the same finding.
  const [reviewTarget, setReviewTarget] = useState<{ url: string; locale: string } | null>(null);

  function reviewPageFromAudit(url: string, locale: string) {
    setReviewTarget({ url, locale });
    setSegment("review");
    setReviewTab("review");
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", fontFamily: "system-ui, sans-serif" }}>
      <nav style={{
        display: "flex", alignItems: "center", gap: 4, padding: "0 16px",
        borderBottom: "1px solid #e5e7eb", height: 48, flexShrink: 0,
      }}>
        <strong style={{ marginRight: 16, fontSize: 14 }}>Content Provenance</strong>
        {SEGMENTS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setSegment(key)}
            style={{
              padding: "6px 14px", fontSize: 13, cursor: "pointer", border: "none",
              background: segment === key ? "#111827" : "transparent",
              color: segment === key ? "white" : "#111827",
              borderRadius: 6, fontWeight: segment === key ? 600 : 400,
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      {segment === "create" && (
        <SubNav tabs={CREATE_TABS} active={createTab} onChange={setCreateTab} />
      )}
      {segment === "review" && (
        <SubNav tabs={REVIEW_TABS} active={reviewTab} onChange={setReviewTab} />
      )}

      <div style={{ flex: 1, overflow: "hidden" }}>
        {segment === "create" && (
          <>
            {createTab === "create" && <div style={{ overflowY: "auto", height: "100%" }}><CreateContentPage /></div>}
            {createTab === "style-guides" && <div style={{ overflowY: "auto", height: "100%" }}><StyleGuidesPage /></div>}
            {createTab === "import" && <div style={{ overflowY: "auto", height: "100%" }}><ImportPage /></div>}
            {createTab === "documents" && <div style={{ overflowY: "auto", height: "100%" }}><DocumentsPage /></div>}
          </>
        )}
        {segment === "review" && (
          <>
            {reviewTab === "review" && <ReviewPage initialFetchTarget={reviewTarget} />}
            {reviewTab === "live" && <LiveReviewPage />}
            {reviewTab === "redrive" && <div style={{ overflowY: "auto", height: "100%" }}><RedriveConsole /></div>}
            {reviewTab === "images" && <div style={{ overflowY: "auto", height: "100%" }}><ImageReview /></div>}
            {reviewTab === "vendors" && <div style={{ overflowY: "auto", height: "100%" }}><VendorScorecardPage /></div>}
            {reviewTab === "consistency" && <div style={{ overflowY: "auto", height: "100%" }}><ConsistencyPage /></div>}
            {reviewTab === "search" && <div style={{ overflowY: "auto", height: "100%" }}><SearchPage /></div>}
            {reviewTab === "dashboard" && <div style={{ overflowY: "auto", height: "100%" }}><Dashboard /></div>}
          </>
        )}
        {segment === "audit" && (
          <div style={{ overflowY: "auto", height: "100%" }}><AuditPage onReviewPage={reviewPageFromAudit} /></div>
        )}
      </div>
    </div>
  );
}

function SubNav<T extends string>({ tabs, active, onChange }: {
  tabs: [T, string][]; active: T; onChange: (t: T) => void;
}) {
  return (
    <nav style={{
      display: "flex", alignItems: "center", gap: 4, padding: "0 16px",
      borderBottom: "1px solid #f3f4f6", height: 40, flexShrink: 0, background: "#fafafa",
    }}>
      {tabs.map(([key, label]) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          style={{
            padding: "5px 10px", fontSize: 12.5, cursor: "pointer", border: "none",
            background: active === key ? "#f3f4f6" : "transparent",
            borderRadius: 5, fontWeight: active === key ? 600 : 400,
          }}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
