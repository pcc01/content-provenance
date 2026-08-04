import { useEffect, useState } from "react";
import { api, type TranslationUnit } from "../api/client";
import { PageFlaggedList } from "../components/PageFlaggedList";
import { SegmentDrawer } from "../components/SegmentDrawer";

type Segment = TranslationUnit & { latest_score: number | null };

// Phase 10: the reviewed page lives in a completely separate browser tab —
// not an iframe this app controls — so there's no ReviewFrame here at
// all. The browser extension's harvest-content-script.ts tags the live
// page and talks to a bridge-content-script.ts injected into THIS page,
// which translates chrome.runtime messages into plain window.postMessage
// — the same {type:"tu:ready"|"tu:selected", ...} shape ReviewFrame.tsx's
// iframe-sourced messages already use, just without an iframe source to
// check (there's nothing to check against — the message comes from this
// page's own extension-injected content script, not a frame).
export function LiveReviewPage() {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [segmentsError, setSegmentsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    async function handleReady(segmentIds: string[]) {
      setConnected(true);
      if (segmentIds.length === 0) return;
      try {
        setSegments(await api.getTranslationsBatch(segmentIds));
      } catch (e) {
        setSegmentsError(e instanceof Error ? e.message : String(e));
      }
    }

    function handler(event: MessageEvent) {
      const msg = event.data;
      if (!msg || typeof msg !== "object") return;
      if (msg.type === "tu:ready") void handleReady(msg.segmentIds);
      if (msg.type === "tu:selected") setSelectedId(msg.tuId);
    }
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  function handlePreview(text: string) {
    if (selectedId) window.postMessage({ type: "tu:preview", tuId: selectedId, text }, "*");
  }

  function handleListSelect(tuId: string) {
    setSelectedId(tuId);
    window.postMessage({ type: "tu:scrollTo", tuId }, "*");
  }

  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{
        width: 280, borderRight: "1px solid #e5e7eb", padding: 12,
        display: "flex", flexDirection: "column", gap: 12, overflowY: "auto", flexShrink: 0,
      }}>
        <p style={{ fontSize: 12, color: "#6b7280", margin: 0 }}>
          Install the browser extension (<code>frontend/extension/</code>, <code>npm run build:extension</code>),
          open the tab you want to review, and click "Start reviewing this tab" in its popup.
          Segments appear here once the extension harvests the page.
        </p>
        <div style={{ fontSize: 12, color: connected ? "#15803d" : "#9ca3af" }}>
          {connected ? "● Connected to a reviewed tab" : "○ Waiting for the extension…"}
        </div>
        {segmentsError && (
          <div style={{ fontSize: 12, color: "#b91c1c", background: "#fef2f2", padding: 8, borderRadius: 6 }}>
            Failed to load segment data: {segmentsError}
          </div>
        )}
        <PageFlaggedList segments={segments} selectedId={selectedId} onSelect={handleListSelect} />
      </div>

      <div style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        color: "#9ca3af", background: "#f3f4f6", textAlign: "center", padding: 24,
      }}>
        The reviewed page renders in its own browser tab (with your real cookies/session) —
        this panel just drives the review over the extension's bridge.
      </div>

      {selectedId && (
        <SegmentDrawer unitId={selectedId} onClose={() => setSelectedId(null)} onPreview={handlePreview} />
      )}
    </div>
  );
}
