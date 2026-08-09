import type { ReactNode } from "react";

// Shared page header: what this page is for, and — critically — whether
// there's a required first step before it does anything. Added because
// several pages (Review, Live Review, Analytics) had no framing at all,
// and the ones that did were inconsistent about calling out required
// inputs vs. "just click the button, nothing to fill in first."
// `requires` renders as a distinct callout so it reads as an instruction,
// not just more description prose; omit it for pages that work with zero
// setup (state that explicitly in `children` instead, e.g. "loads
// automatically" — see VendorScorecardPage/AnalyticsPage) so the absence
// of the callout isn't ambiguous with someone having forgotten to add one.
interface Props {
  title: string;
  children: ReactNode;
  requires?: ReactNode;
  // Narrow sidebar contexts (Review/Live Review) already sit inside a
  // flex column with its own `gap`, so the default marginBottom would
  // double up the spacing — compact drops the outer margin and uses a
  // smaller heading/description size, everything else is identical.
  compact?: boolean;
}

export function PageIntro({ title, children, requires, compact }: Props) {
  return (
    <div style={{ marginBottom: compact ? 0 : 20 }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, fontSize: compact ? 15 : undefined }}>{title}</h2>
      <p style={{ color: "#6b7280", margin: 0, maxWidth: 680, fontSize: compact ? 12.5 : undefined }}>{children}</p>
      {requires && (
        <div
          style={{
            marginTop: 10, padding: "7px 12px", background: "#eff6ff", color: "#1e40af",
            borderRadius: 6, fontSize: 12.5, maxWidth: 680, lineHeight: 1.5,
          }}
        >
          <strong>To get started:</strong> {requires}
        </div>
      )}
    </div>
  );
}
