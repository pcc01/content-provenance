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

export function imageFileUrl(imageId: string): string {
  return `${API_BASE}/images/${imageId}/file`;
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
}

export interface ReviewNote {
  id: string;
  unit_id: string;
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
  format: "text" | "markdown";
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

export const api = {
  getTranslation: (id: string) => request<TranslationUnit>(`/translations/${id}`),
  getTranslationsBatch: (ids: string[]) =>
    request<(TranslationUnit & { latest_score: number | null })[]>(
      `/translations/batch?ids=${encodeURIComponent(ids.join(","))}`,
    ),
  getVersions: (id: string) => request<TranslationUnitVersion[]>(`/translations/${id}/versions`),
  getProvenance: (id: string) => request<ProvenanceResponse>(`/provenance/${id}`),
  getStats: () => request<Stats>("/translations/stats"),

  listNotes: (unitId: string) => request<ReviewNote[]>(`/translations/${unitId}/notes`),
  addNote: (unitId: string, author: string, body: string, parentId?: string) =>
    request<ReviewNote>(`/translations/${unitId}/notes`, {
      method: "POST",
      body: JSON.stringify({ author, body, parent_id: parentId ?? null }),
    }),
  resolveNote: (unitId: string, noteId: string, resolved: boolean) =>
    request<ReviewNote>(`/translations/${unitId}/notes/${noteId}/resolve?resolved=${resolved}`, { method: "PUT" }),

  previewRedrive: (params: { threshold: number; target_language?: string }) =>
    request<RedrivePreview>(
      `/redrive/preview?${new URLSearchParams(params as unknown as Record<string, string>)}`,
    ),
  createRedriveRun: (body: {
    threshold: number;
    scope: Record<string, unknown>;
    require_human_approval?: boolean;
    scoring_provider?: string;
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
    request<QueueItem[]>(`/redrive/queue?${new URLSearchParams(params as unknown as Record<string, string>)}`),

  search: (q: string, semantic = false) =>
    request<{ results: unknown[]; total: number }>(
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

  importDocument: (
    file: File,
    body: { source_language: string; target_language: string; method: string; title?: string },
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", body.source_language);
    form.append("target_language", body.target_language);
    form.append("method", body.method);
    if (body.title) form.append("title", body.title);
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
};
