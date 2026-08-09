// Phase 18 — shared locale list backing every language dropdown in the
// Review Shell. TOP_10 is ranked by total speakers (native + second-
// language) per standard published estimates (Ethnologue-style rankings),
// not by revenue/market size — the ask was "top 10 most spoken," not "top
// 10 markets." One representative region variant is picked per language
// to match this codebase's existing BCP-47-ish convention (en-US, fr-FR,
// ...) — where a language has one obviously-dominant spoken-population
// region (Mandarin -> mainland China, Bengali -> Bangladesh) that's used;
// where the codebase already had an established default elsewhere
// (French -> fr-FR, German -> de-DE), that default is kept for consistency
// rather than picked from scratch.

export interface Locale {
  code: string; // BCP-47-ish, e.g. "fr-FR" — what gets sent to the API
  lang: string; // bare language subtag, e.g. "fr" — for pages (like Audit)
  name: string;
}

export const TOP_10_LOCALES: Locale[] = [
  { code: "en-US", lang: "en", name: "English" },
  { code: "zh-CN", lang: "zh", name: "Mandarin Chinese" },
  { code: "hi-IN", lang: "hi", name: "Hindi" },
  { code: "es-ES", lang: "es", name: "Spanish" },
  { code: "fr-FR", lang: "fr", name: "French" },
  { code: "ar-SA", lang: "ar", name: "Standard Arabic" },
  { code: "bn-BD", lang: "bn", name: "Bengali" },
  { code: "pt-BR", lang: "pt", name: "Portuguese" },
  { code: "ru-RU", lang: "ru", name: "Russian" },
  { code: "ur-PK", lang: "ur", name: "Urdu" },
];

// Everything else selectable, beyond the top 10 default — a reasonably
// broad set of major world/regional languages, not exhaustive. Sorted
// alphabetically by name so it's scannable as a long list.
export const OTHER_LOCALES: Locale[] = [
  { code: "am-ET", lang: "am", name: "Amharic" },
  { code: "cs-CZ", lang: "cs", name: "Czech" },
  { code: "da-DK", lang: "da", name: "Danish" },
  { code: "de-DE", lang: "de", name: "German" },
  { code: "el-GR", lang: "el", name: "Greek" },
  { code: "fa-IR", lang: "fa", name: "Persian" },
  { code: "fi-FI", lang: "fi", name: "Finnish" },
  { code: "fil-PH", lang: "fil", name: "Filipino" },
  { code: "gu-IN", lang: "gu", name: "Gujarati" },
  { code: "he-IL", lang: "he", name: "Hebrew" },
  { code: "hu-HU", lang: "hu", name: "Hungarian" },
  { code: "id-ID", lang: "id", name: "Indonesian" },
  { code: "it-IT", lang: "it", name: "Italian" },
  { code: "ja-JP", lang: "ja", name: "Japanese" },
  { code: "jv-ID", lang: "jv", name: "Javanese" },
  { code: "kn-IN", lang: "kn", name: "Kannada" },
  { code: "ko-KR", lang: "ko", name: "Korean" },
  { code: "ml-IN", lang: "ml", name: "Malayalam" },
  { code: "mr-IN", lang: "mr", name: "Marathi" },
  { code: "ms-MY", lang: "ms", name: "Malay" },
  { code: "nl-NL", lang: "nl", name: "Dutch" },
  { code: "no-NO", lang: "no", name: "Norwegian" },
  { code: "pa-IN", lang: "pa", name: "Punjabi" },
  { code: "pl-PL", lang: "pl", name: "Polish" },
  { code: "pt-PT", lang: "pt-PT", name: "Portuguese (Portugal)" },
  { code: "ro-RO", lang: "ro", name: "Romanian" },
  { code: "sv-SE", lang: "sv", name: "Swedish" },
  { code: "sw-KE", lang: "sw", name: "Swahili" },
  { code: "ta-IN", lang: "ta", name: "Tamil" },
  { code: "te-IN", lang: "te", name: "Telugu" },
  { code: "th-TH", lang: "th", name: "Thai" },
  { code: "tr-TR", lang: "tr", name: "Turkish" },
  { code: "uk-UA", lang: "uk", name: "Ukrainian" },
  { code: "vi-VN", lang: "vi", name: "Vietnamese" },
  { code: "zh-TW", lang: "zh-TW", name: "Chinese (Traditional, Taiwan)" },
];

export const ALL_LOCALES: Locale[] = [...TOP_10_LOCALES, ...OTHER_LOCALES];
