// The minimal cooperative-tagging primitive: spread onto whatever element
// renders a translated string so the overlay (overlay.ts) can find it via
// `[data-tu-id]` and highlight it. Framework-agnostic on purpose — the
// React/i18next-specific convenience wrapper is in useReviewT.ts.
export function reviewTagProps(tuId: string): { "data-tu-id": string } {
  return { "data-tu-id": tuId };
}
