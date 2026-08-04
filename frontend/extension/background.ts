// background.ts — Manifest V3 service worker. Relays messages between
// whichever tab has harvest-content-script.ts active (the page being
// reviewed) and whichever tab has bridge-content-script.ts active (the
// Review Shell's LiveReviewPage). Tracks only ONE of each — matches how
// the Review Shell is a single-page-at-a-time interface (ReviewPage),
// not a multi-session multiplexer. A second reviewer/tab pair would need
// a real pairing scheme; out of scope for this first cut.

let reviewedTabId: number | null = null;
let reviewShellTabId: number | null = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message !== "object") return;

  if (message.type === "review-shell-ready") {
    reviewShellTabId = sender.tab?.id ?? null;
    console.log("[review-extension] Review Shell registered on tab", reviewShellTabId);
    sendResponse({ ok: true });
    return;
  }

  if (message.type === "start-review") {
    reviewedTabId = message.tabId;
    console.log("[review-extension] now reviewing tab", reviewedTabId);
    sendResponse({ ok: true });
    return;
  }

  // Messages FROM the harvest content script (tu:ready, tu:selected) ->
  // relay to the Review Shell tab.
  if (sender.tab?.id === reviewedTabId && reviewShellTabId !== null) {
    chrome.tabs.sendMessage(reviewShellTabId, message).catch(() => {
      // Review Shell tab closed or navigated away — nothing to relay to.
    });
    return;
  }

  // Messages FROM the Review Shell (tu:preview, tu:scrollTo) -> relay to
  // the reviewed tab.
  if (sender.tab?.id === reviewShellTabId && reviewedTabId !== null) {
    chrome.tabs.sendMessage(reviewedTabId, message).catch(() => {
      // Reviewed tab closed or navigated away — nothing to relay to.
    });
    return;
  }
});

// If either tracked tab closes, stop treating it as active — otherwise a
// stale id could relay messages into a tab that's since become something
// else entirely.
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === reviewedTabId) reviewedTabId = null;
  if (tabId === reviewShellTabId) reviewShellTabId = null;
});
