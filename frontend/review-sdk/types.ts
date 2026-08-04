// Shared types for the Review SDK <-> Review Shell postMessage protocol.
// Kept as plain types (no build step) so both the demo-target app and the
// Review Shell can import this file by relative path without a package
// boundary — see frontend/review-sdk/overlay.ts for why.

export interface TranslationSegment {
  id: string;
  source_text: string;
  target_text: string | null;
  target_language: string;
  status: string;
  latest_score: number | null;
  latest_score_reasons: string[];
  has_pending_proposal: boolean;
}

// Overlay (inside the framed page) -> Review Shell (parent)
export type OverlayToShellMessage =
  | { type: "tu:ready"; segmentIds: string[] }
  | { type: "tu:selected"; tuId: string };

// Review Shell (parent) -> Overlay (inside the framed page)
export type ShellToOverlayMessage =
  | { type: "tu:preview"; tuId: string; text: string }
  | { type: "tu:scrollTo"; tuId: string };

export const REVIEW_QUERY_PARAM = "__review";
