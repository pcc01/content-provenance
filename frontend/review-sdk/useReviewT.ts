// React/i18next binding — the intended shape for adopting the Review SDK in
// a real app (e.g. peripateticware, per the plan's Phase 7 test-case pass).
// NOT used by frontend/demo-target, which renders TranslationUnits directly
// without an i18next layer — kept here so the integration shape exists and
// is documented even though nothing in this repo imports it yet (adding it
// as a dependency to a package that doesn't otherwise need react-i18next
// isn't worth doing before there's a real consumer).
//
// Usage in a cooperative app:
//   const t = useReviewT("landing");
//   const { text, tagProps } = t("hero.title");
//   return <h1 {...tagProps}>{text}</h1>;
//
// import { useTranslation } from "react-i18next";
// import { reviewTagProps } from "./reviewTagProps";
//
// export function useReviewT(ns?: string) {
//   const { t } = useTranslation(ns);
//   return function reviewT(key: string, options?: Record<string, unknown>) {
//     return { text: t(key, options), tagProps: reviewTagProps(key) };
//   };
// }
export {};
