// harvest-content-script.ts — injected into the tab being reviewed (Phase
// 10), after review-sdk/dist/overlay.js and harvest.js have already been
// injected first (see popup.ts's chrome.scripting.executeScript call —
// order matters, this script assumes window.ReviewHarvest/window.ReviewSDK
// already exist). Harvests the live DOM, calls the SAME matching endpoint
// Phase 8's Playwright path uses (app/core/page_fetch.py's
// match_or_create_units, exposed as POST /api/v1/pages/harvest), tags
// elements — no text-swap, unlike Phase 8/9's rendered pages, see
// harvest.ts's rewrite() docs for why — and starts the SAME overlay.ts
// used everywhere else, just over a chrome.runtime transport instead of
// postMessage.
//
// Wrapped in an IIFE (not a module — this loads as a classic script via
// chrome.scripting.executeScript's `files` array) so its own API_BASE
// etc. don't collide with any other content script's globals; window.
// ReviewHarvest/window.ReviewSDK are accessed via a type cast rather than
// `declare global`, which needs real module scope to be valid.

(function () {
  interface HarvestedItem {
    idx: number;
    domPath: string;
    text: string;
  }

  interface RewriteEntry {
    tuId: string;
    targetText: string;
  }

  interface ReviewHarvestGlobal {
    harvest(): HarvestedItem[];
    rewrite(mapping: Record<string, RewriteEntry>, swapText: boolean): void;
  }

  interface ReviewSDKGlobal {
    initReviewOverlay(config: {
      apiBase?: string;
      active?: boolean;
      transport?: {
        send: (message: unknown) => void;
        onMessage: (handler: (message: unknown) => void) => void;
      };
    }): void;
  }

  const reviewHarvest = (window as unknown as { ReviewHarvest: ReviewHarvestGlobal }).ReviewHarvest;
  const reviewSDK = (window as unknown as { ReviewSDK: ReviewSDKGlobal }).ReviewSDK;

  // TODO: make configurable (popup settings) for non-local deployments —
  // hardcoded to this project's own documented dev port for now, same as
  // ReviewPage.tsx's DEFAULT_TARGET_BASE and vite.config.ts's proxy target.
  const API_BASE = "http://localhost:8001/api/v1";

  function getStored(key: string, fallback: string): Promise<string> {
    return new Promise((resolve) => {
      chrome.storage.local.get(key, (result) => resolve(result[key] ?? fallback));
    });
  }

  async function run(): Promise<void> {
    const targetLanguage = await getStored("targetLanguage", "fr-FR");
    const sourceLanguage = await getStored("sourceLanguage", "en-US");

    const items = reviewHarvest.harvest();
    console.log("[review-extension] harvested", items.length, "element(s)");
    if (items.length === 0) return;

    let mapping: Record<string, RewriteEntry>;
    try {
      const res = await fetch(`${API_BASE}/pages/harvest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: location.href, source_language: sourceLanguage, target_language: targetLanguage,
          method: "ai", items,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      ({ mapping } = await res.json());
    } catch (e) {
      console.error("[review-extension] harvest matching failed", e);
      return;
    }

    reviewHarvest.rewrite(mapping, false);

    const transport = {
      send(message: unknown): void {
        chrome.runtime.sendMessage(message);
      },
      onMessage(handler: (message: unknown) => void): void {
        chrome.runtime.onMessage.addListener((message) => handler(message));
      },
    };

    reviewSDK.initReviewOverlay({ apiBase: API_BASE, active: true, transport });
  }

  void run();
})();
