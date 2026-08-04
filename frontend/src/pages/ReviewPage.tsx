import { useRef, useState } from "react";
import { api, type TranslationUnit } from "../api/client";
import { PageFlaggedList } from "../components/PageFlaggedList";
import { ReviewFrame, type ReviewFrameHandle } from "../components/ReviewFrame";
import { SegmentDrawer } from "../components/SegmentDrawer";

const DEFAULT_TARGET_BASE = "http://localhost:5174";

type Segment = TranslationUnit & { latest_score: number | null };

// The in-context review environment: the target page renders live in an
// iframe, translated elements get highlight boxes drawn by the injected SDK
// (review-sdk/overlay.ts), and clicking one opens the segment drawer. This
// replaces the segment-grid TMS view that was explicitly rejected as
// unnatural for reviewing real rendered content.
export function ReviewPage() {
  const [targetBase, setTargetBase] = useState(DEFAULT_TARGET_BASE);
  const [route, setRoute] = useState("/");
  const [locale, setLocale] = useState("fr-FR");
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [segmentsError, setSegmentsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const frameRef = useRef<ReviewFrameHandle>(null);

  function loadPage() {
    setSegments([]);
    setSegmentsError(null);
    setSelectedId(null);
    // Cache-bust with a timestamp so clicking "Load page" with unchanged
    // fields still forces the iframe to re-navigate — an unchanged src
    // string is a DOM no-op (no reload) in React, which made it easy to
    // mistake a stale iframe for a broken one while iterating on this page.
    const cacheBust = Date.now();
    setLoadedUrl(`${targetBase}${route}?locale=${encodeURIComponent(locale)}&__review=1&_t=${cacheBust}`);
  }

  async function handleReady(segmentIds: string[]) {
    console.log("[ReviewPage] tu:ready received", segmentIds);
    if (segmentIds.length === 0) return;
    try {
      const results = await api.getTranslationsBatch(segmentIds);
      console.log("[ReviewPage] batch lookup resolved", results.length, "segment(s)");
      setSegments(results);
    } catch (e) {
      console.error("[ReviewPage] batch lookup failed", e);
      setSegmentsError(e instanceof Error ? e.message : String(e));
    }
  }

  function handlePreview(text: string) {
    if (selectedId) frameRef.current?.send({ type: "tu:preview", tuId: selectedId, text });
  }

  function handleListSelect(tuId: string) {
    setSelectedId(tuId);
    frameRef.current?.send({ type: "tu:scrollTo", tuId });
  }

  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{
        width: 280, borderRight: "1px solid #e5e7eb", padding: 12,
        display: "flex", flexDirection: "column", gap: 12, overflowY: "auto", flexShrink: 0,
      }}>
        <div>
          <label style={{ fontSize: 12, color: "#6b7280", display: "block", marginBottom: 2 }}>
            Target app base URL
          </label>
          <input
            value={targetBase} onChange={(e) => setTargetBase(e.target.value)}
            style={{ width: "100%", fontSize: 12, padding: 4, boxSizing: "border-box" }}
          />
        </div>
        <div>
          <label style={{ fontSize: 12, color: "#6b7280", display: "block", marginBottom: 2 }}>Route</label>
          <input
            value={route} onChange={(e) => setRoute(e.target.value)}
            style={{ width: "100%", fontSize: 13, padding: 4, boxSizing: "border-box" }}
          />
        </div>
        <div>
          <label style={{ fontSize: 12, color: "#6b7280", display: "block", marginBottom: 2 }}>Locale</label>
          <input
            value={locale} onChange={(e) => setLocale(e.target.value)}
            style={{ width: "100%", fontSize: 13, padding: 4, boxSizing: "border-box" }}
          />
        </div>
        <button onClick={loadPage} style={{ padding: "6px 0", cursor: "pointer" }}>Load page</button>

        {segmentsError && (
          <div style={{ fontSize: 12, color: "#b91c1c", background: "#fef2f2", padding: 8, borderRadius: 6 }}>
            Failed to load segment data: {segmentsError}
          </div>
        )}
        <PageFlaggedList segments={segments} selectedId={selectedId} onSelect={handleListSelect} />
      </div>

      <div style={{ flex: 1, position: "relative", background: "#f3f4f6" }}>
        {loadedUrl ? (
          <ReviewFrame ref={frameRef} src={loadedUrl} onSelect={setSelectedId} onReady={handleReady} />
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#9ca3af" }}>
            Enter a target app URL and click "Load page" to start reviewing.
          </div>
        )}
      </div>

      {selectedId && (
        <SegmentDrawer unitId={selectedId} onClose={() => setSelectedId(null)} onPreview={handlePreview} />
      )}
    </div>
  );
}
