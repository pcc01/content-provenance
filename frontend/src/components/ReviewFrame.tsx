import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { OverlayToShellMessage, ShellToOverlayMessage } from "../../review-sdk/types";

interface Props {
  src: string;
  onSelect: (tuId: string) => void;
  onReady?: (segmentIds: string[]) => void;
}

export interface ReviewFrameHandle {
  send: (msg: ShellToOverlayMessage) => void;
}

// Loads the target page in a same-origin-in-spirit iframe and speaks the
// overlay.ts postMessage protocol. This is the "loader" — the plan's
// PageLoader interface point: an ExtensionBridgeLoader/ProxyLoader for pages
// that block framing would implement the same onSelect/onReady/send
// contract without SegmentDrawer or the rest of the shell needing to change.
export const ReviewFrame = forwardRef<ReviewFrameHandle, Props>(function ReviewFrame(
  { src, onSelect, onReady },
  ref,
) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useImperativeHandle(ref, () => ({
    send: (msg: ShellToOverlayMessage) => {
      iframeRef.current?.contentWindow?.postMessage(msg, "*");
    },
  }));

  useEffect(() => {
    function handler(event: MessageEvent<OverlayToShellMessage>) {
      // Only accept messages from THIS iframe's own window — without this,
      // any postMessage from anywhere (other extensions, stray iframes,
      // Vite's own tooling) would be processed as if it came from the
      // overlay.
      if (event.source !== iframeRef.current?.contentWindow) {
        console.log("[ReviewFrame] ignored message from a different source:", event.origin, event.data);
        return;
      }
      const msg = event.data;
      if (!msg || typeof msg !== "object") return;
      console.log("[ReviewFrame] message from overlay:", msg);
      if (msg.type === "tu:selected") onSelect(msg.tuId);
      if (msg.type === "tu:ready") onReady?.(msg.segmentIds);
    }
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [onSelect, onReady]);

  return (
    <iframe
      ref={iframeRef}
      src={src}
      title="Reviewed page"
      style={{ width: "100%", height: "100%", border: "none", background: "white" }}
    />
  );
});
