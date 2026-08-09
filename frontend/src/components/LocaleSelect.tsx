import { OTHER_LOCALES, TOP_10_LOCALES } from "../data/locales";

// Phase 18 — every free-text language <input> in the Review Shell replaced
// with this: the top 10 most-spoken languages pinned at the top (so the
// common case is one click), the rest of a broad language list below it,
// and the current value always kept selectable even if it's neither (an
// existing style guide/unit with an unusual locale shouldn't silently
// change when its page re-renders).
interface Props {
  value: string;
  onChange: (v: string) => void;
  // Omit for compact inline rows (e.g. a rule-builder row that already
  // reads left-to-right as type/text/locale/button) — the select still
  // needs SOME accessible name there, so it falls back to aria-label.
  label?: string;
  // "language" = bare subtags (en, fr, ...) for pages that store that
  // shape (Audit's primary_language); default "locale" = full BCP-47-ish
  // (en-US, fr-FR, ...) matching every other page's existing convention.
  variant?: "locale" | "language";
  // Some fields mean "blank = everything" (Redrive's target-language
  // filter, a style guide's applies-to-locale) rather than a required
  // single value — adds a leading "blank" option when set.
  blankLabel?: string;
  width?: number;
}

export function LocaleSelect({ value, onChange, label, variant = "locale", blankLabel, width = 160 }: Props) {
  const field = variant === "language" ? "lang" : "code";
  const top = TOP_10_LOCALES;
  const rest = OTHER_LOCALES;
  const known = new Set([...top, ...rest].map((l) => l[field]));
  const isCustom = value !== "" && !known.has(value);

  const select = (
    <select
      value={value} onChange={(e) => onChange(e.target.value)}
      aria-label={label ?? "Locale"}
      style={{ display: "block", padding: 4, marginTop: label ? 4 : 0, width }}
    >
      {blankLabel !== undefined && <option value="">{blankLabel}</option>}
      {isCustom && <option value={value}>{value} (current)</option>}
      <optgroup label="Most spoken">
        {top.map((l) => <option key={l[field]} value={l[field]}>{l.name}</option>)}
      </optgroup>
      <optgroup label="More languages">
        {rest.map((l) => <option key={l[field]} value={l[field]}>{l.name}</option>)}
      </optgroup>
    </select>
  );

  if (!label) return select;
  return (
    <label style={{ fontSize: 13 }}>
      {label}
      {select}
    </label>
  );
}
