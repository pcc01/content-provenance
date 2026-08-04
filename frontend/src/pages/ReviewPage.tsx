import { useRef, useState } from "react";
import { api, type TranslationUnit } from "../api/client";
import { PageFlaggedList } from "../components/PageFlaggedList";
import { PageHistory } from "../components/PageHistory";
import { ReviewFrame, type ReviewFrameHandle } from "../components/ReviewFrame";
import { SegmentDrawer } from "../components/SegmentDrawer";

const DEFAULT_TARGET_BASE = "http://localhost:5174";

type Segment = TranslationUnit & { latest_score: number | null };
type Mode = "cooperative" | "fetch";

// The in-context review environment: the target page renders live in an
// iframe, translated elements get highlight boxes drawn by the injected SDK
// (review-sdk/overlay.ts), and clicking one opens the segment drawer. This
// replaces the segment-grid TMS view that was explicitly rejected as
// unnatural for reviewing real rendered content.
//
// Two loader modes, both just producing a different iframe `src` for the
// same ReviewFrame — "cooperative" points straight at an app that already
// embeds the SDK (unchanged since Phase 5); "fetch" routes through
// /api/v1/pages/render (Phase 8), which harvests + tags + rewrites ANY
// URL server-side, so no app changes are required at all.
export function ReviewPage() {
  const [mode, setMode] = useState<Mode>("cooperative");

  const [targetBase, setTargetBase] = useState(DEFAULT_TARGET_BASE);
  const [route, setRoute] = useState("/");
  const [locale, setLocale] = useState("fr-FR");

  const [fetchUrl, setFetchUrl] = useState("");
  const [fetchSourceLanguage, setFetchSourceLanguage] = useState("en-US");
  const [fetchMethod, setFetchMethod] = useState("ai");
  const [forceRefresh, setForceRefresh] = useState(false);

  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [loadedFetchTarget, setLoadedFetchTarget] = useState<{ url: string; locale: string } | null>(null);
  const [activeAsOf, setActiveAsOf] = useState<string | null>(null);
  const [pageReady, setPageReady] = useState(false);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [segmentsError, setSegmentsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const frameRef = useRef<ReviewFrameHandle>(null);

  function loadPage() {
    setSegments([]);
    setSegmentsError(null);
    setSelectedId(null);
    setActiveAsOf(null);
    setPageReady(false);
    // Cache-bust with a timestamp so clicking "Load page" with unchanged
    // fields still forces the iframe to re-navigate — an unchanged src
    // string is a DOM no-op (no reload) in React, which made it easy to
    // mistake a stale iframe for a broken one while iterating on this page.
    const cacheBust = Date.now();
    if (mode === "cooperative") {
      setLoadedFetchTarget(null);
      setLoadedUrl(`${targetBase}${route}?locale=${encodeURIComponent(locale)}&__review=1&_t=${cacheBust}`);
    } else {
      setLoadedFetchTarget({ url: fetchUrl, locale });
      const params = new URLSearchParams({
        url: fetchUrl,
        target_language: locale,
        source_language: fetchSourceLanguage,
        method: fetchMethod,
        __review: "1",
        _t: String(cacheBust),
      });
      if (forceRefresh) params.set("refresh", "true");
      setLoadedUrl(`/api/v1/pages/render?${params.toString()}`);
    }
  }

  // Phase 9: reload the same fetched page, optionally pinned to a past
  // point in time. Doesn't re-run loadPage()'s field-reading logic — the
  // target url/locale are whatever was loaded, not necessarily what's
  // still typed into the fields.
  function loadAsOf(asOf: string | null) {
    if (!loadedFetchTarget) return;
    setSegments([]);
    setSegmentsError(null);
    setSelectedId(null);
    setActiveAsOf(asOf);
    setPageReady(false);
    const params = new URLSearchParams({
      url: loadedFetchTarget.url,
      target_language: loadedFetchTarget.locale,
      __review: "1",
      _t: String(Date.now()),
    });
    if (asOf) params.set("as_of", asOf);
    setLoadedUrl(`/api/v1/pages/render?${params.toString()}`);
  }

  async function handleReady(segmentIds: string[]) {
    console.log("[ReviewPage] tu:ready received", segmentIds);
    if (segmentIds.length === 0) return;
    setPageReady(true);
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
        <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", border: "1px solid #e5e7eb" }}>
          <button
            onClick={() => setMode("cooperative")}
            style={{
              flex: 1, padding: "6px 4px", fontSize: 12, cursor: "pointer", border: "none",
              background: mode === "cooperative" ? "#f3f4f6" : "white", fontWeight: mode === "cooperative" ? 600 : 400,
            }}
          >
            SDK-tagged app
          </button>
          <button
            onClick={() => setMode("fetch")}
            style={{
              flex: 1, padding: "6px 4px", fontSize: 12, cursor: "pointer", border: "none",
              background: mode === "fetch" ? "#f3f4f6" : "white", fontWeight: mode === "fetch" ? 600 : 400,
            }}
          >
            Any URL
          </button>
        </div>

        {mode === "cooperative" ? (
          <>
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
          </>
        ) : (
          <>
            <div>
              <label style={{ fontSize: 12, color: "#6b7280", display: "block", marginBottom: 2 }}>
                URL to review
              </label>
              <input
                value={fetchUrl} onChange={(e) => setFetchUrl(e.target.value)}
                placeholder="https://example.com/page"
                style={{ width: "100%", fontSize: 12, padding: 4, boxSizing: "border-box" }}
              />
              <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 4, marginBottom: 0 }}>
                No SDK tagging required — this fetches, harvests, and rewrites the page server-side.
              </p>
            </div>
            <div>
              <label style={{ fontSize: 12, color: "#6b7280", display: "block", marginBottom: 2 }}>
                Source language
              </label>
              <input
                value={fetchSourceLanguage} onChange={(e) => setFetchSourceLanguage(e.target.value)}
                style={{ width: "100%", fontSize: 13, padding: 4, boxSizing: "border-box" }}
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: "#6b7280", display: "block", marginBottom: 2 }}>Method</label>
              <select
                value={fetchMethod} onChange={(e) => setFetchMethod(e.target.value)}
                style={{ width: "100%", fontSize: 13, padding: 4, boxSizing: "border-box" }}
              >
                <option value="ai">ai</option>
                <option value="human">human</option>
                <option value="hybrid">hybrid</option>
              </select>
            </div>
            <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
              <input type="checkbox" checked={forceRefresh} onChange={(e) => setForceRefresh(e.target.checked)} />
              Force refresh (re-fetch instead of using the cached copy)
            </label>
          </>
        )}

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

        {loadedFetchTarget && (
          <PageHistory
            url={loadedFetchTarget.url}
            targetLanguage={loadedFetchTarget.locale}
            activeAsOf={activeAsOf}
            onLoadAsOf={loadAsOf}
            ready={pageReady}
          />
        )}
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
