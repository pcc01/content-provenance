// bridge-content-script.ts — auto-injected into the Review Shell's own
// page (see manifest.json's content_scripts.matches — the app's dev/prod
// origin). Translates between the extension's chrome.runtime messaging
// and the page's own window.postMessage protocol, which
// LiveReviewPage.tsx already listens for (the same OverlayToShellMessage/
// ShellToOverlayMessage shape ReviewFrame.tsx uses for iframe hosting) —
// so the Review Shell's own React code doesn't need to know or care
// whether a message came from an iframe or a real live tab via this
// extension.
//
// Wrapped in an IIFE, same reasoning as harvest-content-script.ts — this
// loads as a classic script, not a module.

(function () {
  chrome.runtime.sendMessage({ type: "review-shell-ready" });

  // FROM the extension (relayed via background.ts from the reviewed tab's
  // harvest-content-script — tu:ready, tu:selected) -> INTO the page as a
  // plain postMessage.
  chrome.runtime.onMessage.addListener((message) => {
    window.postMessage(message, "*");
  });

  // FROM the page (LiveReviewPage.tsx's tu:preview/tu:scrollTo) -> OUT to
  // the extension, which background.ts relays to the reviewed tab.
  // Filtered to these two types specifically so this never re-forwards
  // the messages the listener above just posted INTO the page (which
  // would loop).
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const msg = event.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "tu:preview" || msg.type === "tu:scrollTo") {
      chrome.runtime.sendMessage(msg);
    }
  });
})();
