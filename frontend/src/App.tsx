import { useState } from "react";
import { Dashboard } from "./pages/Dashboard";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ImageReview } from "./pages/ImageReview";
import { LiveReviewPage } from "./pages/LiveReviewPage";
import { RedriveConsole } from "./pages/RedriveConsole";
import { ReviewPage } from "./pages/ReviewPage";
import { SearchPage } from "./pages/SearchPage";

type Tab = "review" | "live" | "redrive" | "images" | "documents" | "search" | "dashboard";

export default function App() {
  const [tab, setTab] = useState<Tab>("review");

  const tabs: [Tab, string][] = [
    ["review", "Review"],
    ["live", "Live (extension)"],
    ["redrive", "Redrive"],
    ["images", "Images"],
    ["documents", "Documents"],
    ["search", "Search"],
    ["dashboard", "Dashboard"],
  ];

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
        {tab === "review" && <ReviewPage />}
        {tab === "live" && <LiveReviewPage />}
        {tab === "redrive" && <div style={{ overflowY: "auto", height: "100%" }}><RedriveConsole /></div>}
        {tab === "images" && <div style={{ overflowY: "auto", height: "100%" }}><ImageReview /></div>}
        {tab === "documents" && <div style={{ overflowY: "auto", height: "100%" }}><DocumentsPage /></div>}
        {tab === "search" && <div style={{ overflowY: "auto", height: "100%" }}><SearchPage /></div>}
        {tab === "dashboard" && <div style={{ overflowY: "auto", height: "100%" }}><Dashboard /></div>}
      </div>
    </div>
  );
}
