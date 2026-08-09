// Typed fetch wrapper for the content-provenance API. In dev, Vite's proxy
// (see vite.config.ts) forwards /api/* to FastAPI on :8000, so relative
// paths work whether this runs under the dev server or a built bundle
// served by FastAPI itself.
const API_BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: init?.body ? { "Content-Type": "application/json", ...(init?.headers ?? {}) } : init?.headers,
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${path} failed (${res.status}): ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Multipart uploads must NOT set Content-Type manually — the browser needs
// to generate the boundary itself, which `request()` above would clobber by
// always forcing application/json whenever a body is present.
async function requestForm<T>(path: string, formData: FormData, method = "POST"): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method, body: formData });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${method} ${path} failed (${res.status}): ${text}`);
  }
  return res.json();
}

// `new URLSearchParams({a: undefined})` does NOT drop the key — it calls
// String(undefined), producing the literal query string `a=undefined`,
// which FastAPI then treats as a real (never-matching) filter value
// instead of "omit this filter." Every optional-param query-string call
// below must route through this first, not pass its params object to
// URLSearchParams directly — caught via live UI testing on the
// Consistency page (blank "target language" silently returned zero
// results instead of everything) before it could ship silently broken.
function cleanParams(params: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) out[k] = String(v);
  }
  return out;
}

export function imageFileUrl(imageId: string): string {
  return `${API_BASE}/images/${imageId}/file`;
}

// Phase 17 — direct download links (not JSON fetches) for the provenance
// exports the backend already generates but nothing linked to before now.
export function xliffDownloadUrl(unitId: string): string {
  return `${API_BASE}/xliff/${unitId}`;
}
export function provJsonDownloadUrl(unitId: string): string {
  return `${API_BASE}/provenance/${unitId}/prov-json`;
}
export function provNDownloadUrl(unitId: string): string {
  return `${API_BASE}/provenance/${unitId}/prov-n`;
}

export interface TranslationUnit {
  id: string;
  source_id: string;
  source_text: string;
  source_language: string;
  target_text: string | null;
  target_language: string;
  translation_method: string;
  translated_by_agent_id: string;
  translated_at: string | null;
  reviewed_by_agent_id: string | null;
  reviewed_at: string | null;
  confidence_score: number | null;
  quality_score: number | null;
  status: string;
  metadata: Record<string, unknown>;
}

export interface TranslationUnitVersion {
  id: string;
  unit_id: string;
  version_number: number;
  target_text: string;
  translated_by_agent_id: string;
  method: string;
  created_at: string;
  source_event: string;
  quality_score: number | null;
  note: string | null;
}

export interface ProvenanceEntity {
  id: string;
  entity_type: string;
  generated_at: string;
  attributes: Record<string, unknown>;
}

export interface ProvenanceActivity {
  id: string;
  activity_type: string;
  started_at: string;
  ended_at: string | null;
}

export interface ProvenanceAgent {
  id: string;
  name: string;
  agent_type: string;
  model_version: string | null;
  organization: string | null;
}

export interface DeploymentRecord {
  id: string;
  translation_unit_id: string;
  context: string;
  location: string;
  deployed_at: string;
  deployed_by: string | null;
  version: string | null;
  is_active: boolean;
  retired_at: string | null;
}

export interface ProvenanceResponse {
  translation_unit_id: string;
  source_text: string;
  target_text: string | null;
  provenance: {
    bundle_id: string;
    generated_at: string;
    summary: string | null;
    entities: ProvenanceEntity[];
    activities: ProvenanceActivity[];
    agents: ProvenanceAgent[];
    relations: Record<string, string>[];
  };
  deployments: DeploymentRecord[];
}

export interface LineageNode {
  id: string;
  label: string;
  type: "entity" | "activity" | "agent";
}

export interface LineageEdge {
  from: string;
  to: string;
  label: string;
}

export interface LineageGraph {
  translation_unit_id: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
  summary: string | null;
}

export interface IngestEvent {
  id: string;
  direction: "in" | "out";
  format: string;
  source_system: string | null;
  xliff_document_id: string | null;
  unit_count: number;
  created_at: string;
}

export interface ReviewNote {
  id: string;
  unit_id: string | null;
  page_url: string | null;
  target_language: string | null;
  author: string;
  body: string;
  created_at: string;
  resolved: boolean;
  parent_id: string | null;
}

export interface RedriveRunItem {
  id: string;
  run_id: string;
  unit_id: string;
  before_score: number | null;
  after_score: number | null;
  outcome: string;
  detail: string | null;
  proposed_text: string | null;
  approved_by: string | null;
  approved_at: string | null;
}

export interface RedriveRun {
  id: string;
  status: string;
  threshold: number;
  style_threshold: number | null;
  style_guide_id: string | null;
  scope: Record<string, unknown>;
  scoring_provider: string;
  redrive_provider: string;
  require_human_approval: boolean;
  started_at: string;
  finished_at: string | null;
  summary: Record<string, number>;
  items: RedriveRunItem[];
}

export interface RedrivePreview {
  scope_count: number;
  below_threshold: number;
  below_style_threshold?: number;
  estimated_source_chars: number;
  redrive_provider: string;
}

export interface QueueItem {
  unit_id: string;
  score: number;
  reasons: string[];
  source_text: string;
  target_text: string | null;
  target_language: string;
  scored_at: string;
}

export interface Stats {
  total_translations: number;
  by_method: Record<string, number>;
  by_status: Record<string, number>;
  total_deployments: number;
  total_projects: number;
  total_agents: number;
}

export interface ImageAsset {
  id: string;
  kind: "context" | "translatable";
  storage_path: string;
  content_type: string;
  checksum: string;
  original_filename: string | null;
  alt_text: string | null;
  uploaded_at: string;
  uploaded_by: string | null;
}

export interface ImageContextLink {
  id: string;
  image_id: string;
  translation_unit_id: string;
  note: string | null;
  created_at: string;
}

export interface ImageTranslationUnit {
  id: string;
  source_image_id: string;
  target_image_id: string | null;
  source_language: string;
  target_language: string;
  translation_method: string;
  translated_by_agent_id: string;
  translated_at: string | null;
  status: string;
  overlay_text_unit_ids: string[];
}

export interface DocumentMeta {
  id: string;
  title: string;
  original_filename: string | null;
  format: "text" | "markdown" | "csv";
  source_language: string;
  created_at: string;
  uploaded_by: string | null;
}

export interface DocumentSegments {
  document: DocumentMeta;
  segments: TranslationUnit[];
}

export interface PageHistory {
  url: string;
  target_language: string;
  timestamps: string[];
}

export interface PageDiffChange {
  unit_id: string;
  source_text: string | null;
  before_text: string | null;
  after_text: string | null;
}

export interface PageDiff {
  url: string;
  target_language: string;
  changes: PageDiffChange[];
}

export interface PendingChange {
  item_id: string;
  run_id: string;
  unit_id: string;
  source_text: string | null;
  current_text: string | null;
  proposed_text: string | null;
}

export interface PendingChanges {
  url: string;
  target_language: string;
  pending: PendingChange[];
}

export interface BulkApproveResult {
  item_id: string;
  ok: boolean;
  error?: string;
}

export type SiteAuditCheck =
  | "mixed_locale" | "rtl_readiness" | "icu_i18n" | "privacy"
  | "text_expansion" | "font_coverage" | "hreflang" | "cookie_consent"
  | "placeholder_leak" | "locale_format" | "translation_coverage"
  | "locale_switcher" | "seo_metadata" | "payment_localization";
export type SiteAuditSeverity = "info" | "warning" | "critical";
export type SiteAuditStatus = "pending" | "running" | "completed" | "failed";

export interface SiteAudit {
  id: string;
  root_url: string;
  primary_language: string;
  max_pages: number;
  checks: SiteAuditCheck[];
  status: SiteAuditStatus;
  requester_email: string | null;
  triggered_by: string | null;
  started_at: string;
  finished_at: string | null;
  pages_crawled: number;
  error: string | null;
  blocked: boolean;
}

export interface SiteAuditPage {
  id: string;
  audit_id: string;
  url: string;
  html_lang_attr: string | null;
  expected_locale: string | null;
  detected_language: string | null;
  status_code: number | null;
  fetched_at: string;
}

export interface SiteAuditFinding {
  id: string;
  audit_id: string;
  page_id: string | null;
  check: SiteAuditCheck;
  finding_type: string;
  severity: SiteAuditSeverity;
  summary: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface AuditRunSummary {
  audit: SiteAudit;
  findings_by_check: Record<string, number>;
  findings_by_severity: Record<string, number>;
}

export function auditExportUrl(auditId: string): string {
  return `${API_BASE}/audit/runs/${auditId}/export`;
}

export function auditPdfUrl(auditId: string): string {
  return `${API_BASE}/audit/runs/${auditId}/report.pdf`;
}

// ── Phase 13: Style Guides / Glossary / Retrieval ───────────────────────────

export interface StyleGuide {
  id: string;
  name: string;
  version: string;
  locale: string | null;
  voice_description: string | null;
  tone_attributes: Record<string, unknown>;
  supersedes_id: string | null;
  created_at: string;
  created_by: string | null;
}

export interface StyleGuideRule {
  id: string;
  style_guide_id: string;
  rule_type: "tone" | "voice" | "terminology" | "formatting";
  rule_text: string;
  severity: "minor" | "major" | "critical";
  applies_to_locale: string | null;
  source_term: string | null;
  target_term: string | null;
  created_at: string;
}

export interface GlossaryTerm {
  id: string;
  style_guide_id: string | null;
  source_term: string;
  target_term: string | null;
  locale: string | null;
  do_not_translate: boolean;
  notes: string | null;
  created_at: string;
}

export interface RetrievedFact {
  kind: "rule" | "term" | "exemplar";
  id: string;
  text: string;
  source: string;
}

export interface RetrievePreview {
  rules: RetrievedFact[];
  terms: RetrievedFact[];
  exemplars: RetrievedFact[];
  prompt_context: string;
}

export interface CheckSourceResult {
  tone_score: number | null;
  voice_score: number | null;
  overall_score: number | null;
  reasons: string[];
  style_guide_id: string | null;
  needs_review: boolean;
}

// ── Phase 14: Vendor Scorecard / Consistency ────────────────────────────────

export interface VendorScorecardEntry {
  organization: string;
  unit_count: number;
  avg_quality_score: number | null;
  avg_style_score: number | null;
  avg_tone_score: number | null;
  avg_voice_score: number | null;
  avg_terminology_score: number | null;
}

export interface ConsistencyFinding {
  id: string;
  finding_type: "term_drift" | "term_inconsistency" | "tone_spread";
  severity: "info" | "warning";
  summary: string;
  unit_ids: string[];
  detail: Record<string, unknown>;
}

export interface ConsistencyResult {
  scope: Record<string, unknown>;
  units_checked: number;
  findings: ConsistencyFinding[];
  checked_at: string;
}

// ── Phase 15: Automatic Quality Metrics ─────────────────────────────────────

export interface AutomaticMetricScore {
  id: string;
  unit_id: string;
  metric: string;
  score: number | null;
  raw_score: number | null;
  reference_type: string | null;
  scored_at: string;
}

// ── Phase 16: multi-provider translate / evaluate / retranslate ────────────
//
// Two distinct provider vocabularies on the backend, not one: a TRANSLATE
// provider is anything with a TranslationBackend (app/core/translation_
// backends.py's _PROVIDER_CLASSES) — includes NMT-only services (Google
// Translate, MS Translator) that can't evaluate. An EVALUATE provider is
// anything with a QualityScorer (app/core/scoring/factory.py's get_scorer)
// — notably "claude", not "anthropic", for the same underlying vendor,
// because the two factories were named independently. Getting this wrong
// (e.g. sending "anthropic" to /quality/evaluate) 400s, so the two option
// lists below are kept deliberately separate rather than merged.

export const TRANSLATE_PROVIDERS: { value: string; label: string }[] = [
  { value: "", label: "Default (app setting)" },
  { value: "anthropic", label: "Claude (Anthropic)" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Google Gemini" },
  { value: "google", label: "Google Translate (NMT only)" },
  { value: "deepl", label: "DeepL" },
  { value: "mstranslator", label: "Microsoft Translator (NMT only)" },
  { value: "ollama", label: "Ollama — Tower+ (local)" },
  { value: "lmstudio", label: "LMStudio (local)" },
  { value: "vllm", label: "vLLM (local)" },
];

export const EVALUATE_PROVIDERS: { value: string; label: string }[] = [
  { value: "", label: "Default (app setting)" },
  { value: "claude", label: "Claude (Anthropic)" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Google Gemini" },
  { value: "ollama", label: "Ollama — Tower+ (local)" },
  { value: "lmstudio", label: "LMStudio (local)" },
  { value: "vllm", label: "vLLM (local)" },
];

export interface EvaluateResult {
  id: string;
  unit_id: string;
  score: number | null;
  scorer: string;
  reasons: string[];
  needs_review: boolean;
  hard_fail: boolean;
  raw_response: string | null;
}

// ── Phase 18: model discovery ───────────────────────────────────────────────
//
// Every provider that actually offers more than one selectable model —
// the three local multi-model servers PLUS the three hosted vendors
// (Claude/OpenAI/Gemini each ship multiple generations/sizes too, not
// just Ollama/LMStudio/vLLM). DeepL/Google Translate/MS Translator are
// pure single-endpoint NMT — no model to pick, so they're excluded and
// ModelPicker.tsx never shows a model dropdown for them.
export const MODEL_DISCOVERABLE_PROVIDERS = new Set([
  "anthropic", "claude", "openai", "gemini", "ollama", "lmstudio", "vllm",
]);

export interface ModelListResponse {
  provider: string;
  models: string[];
}

export function vendorScorecardPdfUrl(targetLanguage?: string): string {
  return `${API_BASE}/vendors/scorecard/report.pdf${targetLanguage ? `?target_language=${encodeURIComponent(targetLanguage)}` : ""}`;
}

// POST /translations/'s response — was never wrapped by the original
// client (no "create a translation" form existed anywhere in the UI until
// the Content Creation page), added here alongside the Phase 13 additions
// that make it worth having a dedicated creation screen for.
export interface TranslateResponse {
  translation_unit_id: string;
  source_text: string;
  translated_text: string;
  source_language: string;
  target_language: string;
  method: string;
  confidence_score: number | null;
  provenance_record_id: string;
  xliff_document_id: string;
  status: string;
  translated_at: string;
}

const phase13to15Api = {
  createTranslation: (body: {
    source_text: string; source_language: string; target_language: string;
    method?: "ai" | "human" | "hybrid"; context?: string; style_guide_id?: string; domain?: string;
    provider?: string; // Phase 16 — overrides settings.translation_provider for this call only
    model?: string; // Phase 18 — which model within provider (see MODEL_DISCOVERABLE_PROVIDERS)
  }) => request<TranslateResponse>("/translations/", { method: "POST", body: JSON.stringify(body) }),

  // Phase 18 — live "what's actually available" for a given provider; see
  // MODEL_DISCOVERABLE_PROVIDERS for which ones have anything to list.
  getModels: (provider: string) => request<ModelListResponse>(`/models/${provider}`),

  // ── Style Guides ───────────────────────────────────────────────────────
  listStyleGuides: (locale?: string) =>
    request<StyleGuide[]>(`/style/guides${locale ? `?locale=${encodeURIComponent(locale)}` : ""}`),
  createStyleGuide: (body: {
    name: string; version?: string; locale?: string; voice_description?: string;
    tone_attributes?: Record<string, unknown>; supersedes_id?: string; created_by?: string;
  }) => request<StyleGuide>("/style/guides", { method: "POST", body: JSON.stringify(body) }),
  getStyleGuideChain: (id: string) => request<StyleGuide[]>(`/style/guides/${id}/chain`),

  listStyleGuideRules: (guideId: string, locale?: string) =>
    request<StyleGuideRule[]>(`/style/guides/${guideId}/rules${locale ? `?locale=${encodeURIComponent(locale)}` : ""}`),
  createStyleGuideRule: (guideId: string, body: {
    rule_type: string; rule_text: string; severity?: string; applies_to_locale?: string;
    source_term?: string; target_term?: string;
  }) => request<StyleGuideRule>(`/style/guides/${guideId}/rules`, { method: "POST", body: JSON.stringify(body) }),

  listGlossaryTerms: (params?: { style_guide_id?: string; locale?: string }) =>
    request<GlossaryTerm[]>(
      `/style/glossary-terms${params ? `?${new URLSearchParams(cleanParams(params))}` : ""}`,
    ),
  createGlossaryTerm: (body: {
    source_term: string; target_term?: string; locale?: string; do_not_translate?: boolean;
    notes?: string; style_guide_id?: string; preferred_over_term_ids?: string[];
  }) => request<GlossaryTerm>("/style/glossary-terms", { method: "POST", body: JSON.stringify(body) }),

  retrievePreview: (params: { text: string; source_language: string; target_language: string; style_guide_id?: string }) =>
    request<RetrievePreview>(`/style/retrieve-preview?${new URLSearchParams(cleanParams(params))}`),
  checkSource: (body: { text: string; language: string; style_guide_id?: string }) =>
    request<CheckSourceResult>("/style/check-source", { method: "POST", body: JSON.stringify(body) }),

  // ── TMX / XLIFF import ────────────────────────────────────────────────
  importTmx: (file: File, body: { source_language: string; target_language: string; source_system: string; style_guide_id?: string }) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", body.source_language);
    form.append("target_language", body.target_language);
    form.append("source_system", body.source_system);
    if (body.style_guide_id) form.append("style_guide_id", body.style_guide_id);
    return requestForm<{ imported_count: number; exemplar_ids: string[] }>("/tm/import", form);
  },
  importXliff: (file: File, sourceSystem: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_system", sourceSystem);
    return requestForm<{ imported_count: number; translation_unit_ids: string[] }>("/xliff/import", form);
  },

  // Phase 17 — the queryable side of the "everything entering and leaving
  // the system" XLIFF ledger; every import/export above logs into it.
  getIngestLog: (limit = 100) => request<IngestEvent[]>(`/xliff/ingest-log?limit=${limit}`),
  xliffPreview: (unitId: string) => request<{ xliff: string }>(`/xliff/${unitId}/preview`),

  // ── Vendor Scorecard ───────────────────────────────────────────────────
  getVendorScorecard: (targetLanguage?: string) =>
    request<VendorScorecardEntry[]>(
      `/vendors/scorecard${targetLanguage ? `?target_language=${encodeURIComponent(targetLanguage)}` : ""}`,
    ),

  // ── Consistency ────────────────────────────────────────────────────────
  checkConsistency: (params: { target_language?: string; source_language?: string; project_id?: string; unit_ids?: string }) =>
    request<ConsistencyResult>(`/consistency/check?${new URLSearchParams(cleanParams(params))}`),

  // ── Automatic metrics ──────────────────────────────────────────────────
  meteorCompare: (hypothesis: string, reference: string) =>
    request<{ score: number | null }>("/quality/meteor-compare", {
      method: "POST", body: JSON.stringify({ hypothesis, reference }),
    }),
  getAutomaticScores: (unitId: string) => request<AutomaticMetricScore[]>(`/quality/${unitId}/automatic`),

  // Phase 16 — standalone "evaluate" action: score one unit with a chosen
  // LLM-judge provider on demand, independent of a redrive run.
  evaluateUnit: (unitId: string, provider?: string, model?: string) =>
    request<EvaluateResult>("/quality/evaluate", {
      method: "POST", body: JSON.stringify({ unit_id: unitId, provider: provider || undefined, model: model || undefined }),
    }),
};

export const api = {
  ...phase13to15Api,

  getTranslation: (id: string) => request<TranslationUnit>(`/translations/${id}`),
  getTranslationsBatch: (ids: string[]) =>
    request<(TranslationUnit & { latest_score: number | null; has_pending_proposal: boolean })[]>(
      `/translations/batch?ids=${encodeURIComponent(ids.join(","))}`,
    ),
  getVersions: (id: string) => request<TranslationUnitVersion[]>(`/translations/${id}/versions`),
  getProvenance: (id: string) => request<ProvenanceResponse>(`/provenance/${id}`),
  getLineage: (id: string) => request<LineageGraph>(`/provenance/${id}/lineage`),
  getDeployments: (id: string) => request<DeploymentRecord[]>(`/provenance/${id}/deployments`),
  recordDeployment: (unitId: string, params: {
    context: string; location: string; deployed_by?: string; version?: string;
  }) => request<{ message: string }>(
    `/translations/${unitId}/deploy?${new URLSearchParams(cleanParams(params))}`, { method: "POST" },
  ),
  // quality_score is optional context for the record, not a re-score —
  // the unit's actual score still comes from the scoring providers.
  markReviewed: (unitId: string, reviewerName: string, qualityScore?: number) =>
    request<{ message: string; reviewed_by: string; status: string }>(
      `/translations/${unitId}/review?${new URLSearchParams(cleanParams({ reviewer_name: reviewerName, quality_score: qualityScore }))}`,
      { method: "PUT" },
    ),
  getStats: () => request<Stats>("/translations/stats"),

  listNotes: (unitId: string) => request<ReviewNote[]>(`/translations/${unitId}/notes`),
  addNote: (unitId: string, author: string, body: string, parentId?: string) =>
    request<ReviewNote>(`/translations/${unitId}/notes`, {
      method: "POST",
      body: JSON.stringify({ author, body, parent_id: parentId ?? null }),
    }),
  resolveNote: (unitId: string, noteId: string, resolved: boolean) =>
    request<ReviewNote>(`/translations/${unitId}/notes/${noteId}/resolve?resolved=${resolved}`, { method: "PUT" }),

  previewRedrive: (params: {
    threshold: number; style_threshold?: number; style_guide_id?: string; target_language?: string;
    scoring_provider?: string; scoring_model?: string;
  }) =>
    request<RedrivePreview>(
      `/redrive/preview?${new URLSearchParams(cleanParams(params))}`,
    ),
  createRedriveRun: (body: {
    threshold: number;
    // Phase 13 — independent style-adherence axis; a unit redrives if
    // EITHER threshold is crossed. undefined/omitted = style is never
    // itself a reason to redrive (see RedriveRun.style_threshold's
    // docstring on the backend).
    style_threshold?: number;
    style_guide_id?: string;
    scope: Record<string, unknown>;
    require_human_approval?: boolean;
    scoring_provider?: string; // the "evaluate" model — see EVALUATE_PROVIDERS
    redrive_provider?: string; // Phase 16 — the "retranslate" model — see TRANSLATE_PROVIDERS
    scoring_model?: string; // Phase 18 — which model within scoring_provider
    redrive_model?: string; // Phase 18 — which model within redrive_provider
  }) => request<RedriveRun>("/redrive/runs", { method: "POST", body: JSON.stringify(body) }),
  getRedriveRun: (id: string) => request<RedriveRun>(`/redrive/runs/${id}`),
  approveRedriveItem: (runId: string, itemId: string, actor: string) =>
    request<RedriveRunItem>(`/redrive/runs/${runId}/items/${itemId}/approve`, {
      method: "POST", body: JSON.stringify({ actor }),
    }),
  rejectRedriveItem: (runId: string, itemId: string, actor: string, reason?: string) =>
    request<RedriveRunItem>(`/redrive/runs/${runId}/items/${itemId}/reject`, {
      method: "POST", body: JSON.stringify({ actor, reason }),
    }),
  getQueue: (params: { threshold: number; target_language?: string }) =>
    request<QueueItem[]>(`/redrive/queue?${new URLSearchParams(cleanParams(params))}`),

  search: (q: string, semantic = false) =>
    request<{ results: unknown[]; total: number; indexed_documents: number; search_type: string }>(
      `/search/?${new URLSearchParams({ q, semantic: String(semantic) })}`,
    ),

  uploadImage: (file: File, kind: "context" | "translatable", altText?: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (altText) form.append("alt_text", altText);
    return requestForm<ImageAsset>("/images/", form);
  },
  getImage: (imageId: string) => request<ImageAsset>(`/images/${imageId}`),
  localizeImage: (
    imageId: string,
    body: { source_language: string; target_language: string; method: string; translator_name?: string },
    targetFile?: File,
  ) => {
    const form = new FormData();
    form.append("source_language", body.source_language);
    form.append("target_language", body.target_language);
    form.append("method", body.method);
    if (body.translator_name) form.append("translator_name", body.translator_name);
    if (targetFile) form.append("target_file", targetFile);
    return requestForm<ImageTranslationUnit>(`/images/${imageId}/localize`, form);
  },
  attachLocalizedImage: (ituId: string, targetFile: File) => {
    const form = new FormData();
    form.append("target_file", targetFile);
    return requestForm<ImageTranslationUnit>(`/images/localize/${ituId}/target`, form, "PUT");
  },
  getImageTranslationUnit: (ituId: string) => request<ImageTranslationUnit>(`/images/localize/${ituId}`),

  // Phase 17 — "this screenshot shows this text segment in context," for
  // the review UI. Distinct from uploadImage's kind="translatable" path
  // above (a standalone banner/graphic with its own provenance chain).
  linkImageAsContext: (imageId: string, translationUnitId: string, note?: string) => {
    const form = new FormData();
    form.append("translation_unit_id", translationUnitId);
    if (note) form.append("note", note);
    return requestForm<ImageContextLink>(`/images/${imageId}/context-link`, form);
  },
  getContextImages: (unitId: string) => request<ImageAsset[]>(`/images/context-links/${unitId}`),

  importDocument: (
    file: File,
    body: {
      source_language: string; target_language: string; method: string; title?: string;
      source_column?: string; // Phase 18 — CSV only: which column holds the source text
    },
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", body.source_language);
    form.append("target_language", body.target_language);
    form.append("method", body.method);
    if (body.title) form.append("title", body.title);
    if (body.source_column) form.append("source_column", body.source_column);
    return requestForm<DocumentMeta>("/documents/import", form);
  },
  getDocument: (documentId: string) => request<DocumentMeta>(`/documents/${documentId}`),
  getDocumentSegments: (documentId: string, targetLanguage: string) =>
    request<DocumentSegments>(
      `/documents/${documentId}/segments?target_language=${encodeURIComponent(targetLanguage)}`,
    ),

  revertVersion: (unitId: string, versionId: string, revertedBy?: string) =>
    request<TranslationUnit>(
      `/translations/${unitId}/versions/${versionId}/revert${revertedBy ? `?reverted_by=${encodeURIComponent(revertedBy)}` : ""}`,
      { method: "POST" },
    ),

  getPageHistory: (url: string, targetLanguage: string) =>
    request<PageHistory>(
      `/pages/history?${new URLSearchParams({ url, target_language: targetLanguage })}`,
    ),
  getPageDiff: (url: string, targetLanguage: string, fromTs: string, toTs: string) =>
    request<PageDiff>(
      `/pages/diff?${new URLSearchParams({ url, target_language: targetLanguage, from_ts: fromTs, to_ts: toTs })}`,
    ),

  proposeTranslation: (unitId: string, proposedText: string, proposedBy: string) =>
    request<RedriveRunItem>("/redrive/propose", {
      method: "POST",
      body: JSON.stringify({ unit_id: unitId, proposed_text: proposedText, proposed_by: proposedBy }),
    }),

  getPendingChanges: (url: string, targetLanguage: string) =>
    request<PendingChanges>(`/pages/pending?${new URLSearchParams({ url, target_language: targetLanguage })}`),
  bulkApproveItems: (itemIds: string[], actor: string) =>
    request<{ results: BulkApproveResult[] }>("/redrive/items/bulk-approve", {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds, actor }),
    }),

  getPageNotes: (url: string, targetLanguage: string) =>
    request<ReviewNote[]>(`/pages/notes?${new URLSearchParams({ url, target_language: targetLanguage })}`),
  addPageNote: (url: string, targetLanguage: string, author: string, body: string, parentId?: string) =>
    request<ReviewNote>("/pages/notes", {
      method: "POST",
      body: JSON.stringify({ url, target_language: targetLanguage, author, body, parent_id: parentId ?? null }),
    }),
  resolvePageNote: (noteId: string, resolved: boolean) =>
    request<ReviewNote>(`/pages/notes/${noteId}/resolve?resolved=${resolved}`, { method: "PUT" }),

  createAuditRun: (body: {
    root_url: string; primary_language: string; requester_email: string; max_pages?: number;
    checks?: SiteAuditCheck[]; triggered_by?: string;
    // Phase 18 — optional, per-run only, never stored: "bring your own
    // authenticated session" for sites that gate content behind a login
    // or bot-detection wall. Anonymous crawling (all three omitted) is
    // unchanged and remains the default.
    auth_username?: string; auth_password?: string; auth_cookie?: string;
  }) => request<SiteAudit>("/audit/runs", { method: "POST", body: JSON.stringify(body) }),
  listAuditRuns: () => request<SiteAudit[]>("/audit/runs"),
  getAuditRun: (id: string) => request<AuditRunSummary>(`/audit/runs/${id}`),
  getAuditPages: (id: string) => request<SiteAuditPage[]>(`/audit/runs/${id}/pages`),
  getAuditFindings: (id: string, params?: { check?: SiteAuditCheck; severity?: SiteAuditSeverity }) =>
    request<SiteAuditFinding[]>(
      `/audit/runs/${id}/findings${params ? `?${new URLSearchParams(cleanParams(params))}` : ""}`,
    ),
};
