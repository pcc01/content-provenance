// Review SDK — the in-context visual overlay.
//
// Activates when the host page is loaded with ?__review=1 (see
// REVIEW_QUERY_PARAM), or when a caller passes `active: true` explicitly
// (Phase 10's browser extension has no URL to put a query param on — the
// reviewer activates it via the toolbar icon instead). Queries [data-tu-id]
// elements already present in the DOM (attached by the target app itself —
// see useReviewT.ts, or Phase 8/10's harvest.ts), draws absolutely-positioned
// highlight boxes directly inside THIS document (not the parent's —
// cross-frame geometry sync is fragile; drawing locally next to the
// elements it tracks is not), color-coded by quality score, and talks to
// the Review Shell over a pluggable transport.
//
// This file has no build step and no framework dependency on purpose: it
// needs to run inside whatever page it's dropped into, cooperative apps
// range from React to plain HTML, and keeping it dependency-free is what
// makes the "start cooperative, extend later" plan viable — the loader can
// change (iframe now, extension later) without this contract changing. The
// transport abstraction is exactly that seam for HOW messages travel:
// default is postMessage (iframe hosting, Phase 5/8/9 unchanged); Phase
// 10's extension content script supplies a chrome.runtime-based one
// instead — the box-drawing/click logic itself doesn't change either way.

import type { OverlayToShellMessage, ShellToOverlayMessage, TranslationSegment } from "./types";
import { REVIEW_QUERY_PARAM } from "./types";

export interface ReviewTransport {
  send(message: OverlayToShellMessage): void;
  onMessage(handler: (message: ShellToOverlayMessage) => void): void;
}

class PostMessageTransport implements ReviewTransport {
  send(message: OverlayToShellMessage): void {
    window.parent.postMessage(message, "*");
  }

  onMessage(handler: (message: ShellToOverlayMessage) => void): void {
    window.addEventListener("message", (event: MessageEvent<ShellToOverlayMessage>) => {
      const msg = event.data;
      if (msg && typeof msg === "object") handler(msg);
    });
  }
}

export interface ReviewOverlayConfig {
  apiBase?: string; // defaults to same-origin "/api/v1"
  transport?: ReviewTransport; // defaults to postMessage (iframe hosting)
  active?: boolean; // defaults to checking ?__review=1 in the URL
}

const BOX_LAYER_ID = "__review_overlay_layer";

function isReviewMode(): boolean {
  return new URLSearchParams(window.location.search).get(REVIEW_QUERY_PARAM) === "1";
}

function scoreColor(score: number | null): string {
  if (score === null) return "#8a8a8a"; // unscored — neutral gray
  if (score < 50) return "#e5484d"; // red
  if (score < 80) return "#f5a524"; // yellow
  return "#30a46c"; // green
}

class ReviewOverlay {
  private apiBase: string;
  private transport: ReviewTransport;
  private layer: HTMLDivElement;
  private segments = new Map<string, TranslationSegment>();
  private boxes = new Map<string, HTMLDivElement>();
  private rafId: number | null = null;

  constructor(config: ReviewOverlayConfig) {
    this.apiBase = config.apiBase ?? "/api/v1";
    this.transport = config.transport ?? new PostMessageTransport();
    this.layer = this.createLayer();
  }

  private createLayer(): HTMLDivElement {
    const existing = document.getElementById(BOX_LAYER_ID) as HTMLDivElement | null;
    if (existing) return existing;
    const layer = document.createElement("div");
    layer.id = BOX_LAYER_ID;
    layer.style.position = "absolute";
    layer.style.top = "0";
    layer.style.left = "0";
    layer.style.width = "0";
    layer.style.height = "0";
    layer.style.zIndex = "2147483647";
    layer.style.pointerEvents = "none";
    document.body.appendChild(layer);
    return layer;
  }

  async start(): Promise<void> {
    const elements = Array.from(document.querySelectorAll<HTMLElement>("[data-tu-id]"));
    const ids = Array.from(new Set(elements.map((el) => el.dataset.tuId!).filter(Boolean)));
    console.log("[review-sdk] start() found", elements.length, "tagged element(s),", ids.length, "unique id(s)");
    if (ids.length === 0) return;

    await this.fetchSegments(ids);
    for (const el of elements) {
      const tuId = el.dataset.tuId!;
      if (this.segments.has(tuId)) this.attachBox(el, tuId);
    }

    window.addEventListener("scroll", this.scheduleReposition, { passive: true });
    window.addEventListener("resize", this.scheduleReposition);
    this.transport.onMessage(this.handleShellMessage);

    console.log("[review-sdk] posting tu:ready with", ids.length, "segment(s) to parent");
    this.transport.send({ type: "tu:ready", segmentIds: ids });
  }

  private async fetchSegments(ids: string[]): Promise<void> {
    try {
      const res = await fetch(`${this.apiBase}/translations/batch?ids=${encodeURIComponent(ids.join(","))}`);
      if (!res.ok) return;
      const results: TranslationSegment[] = await res.json();
      for (const seg of results) this.segments.set(seg.id, seg);
    } catch {
      // Network hiccup or the API not reachable from this origin — the page
      // still renders normally, it just won't get review highlight boxes.
    }
  }

  private attachBox(el: HTMLElement, tuId: string): void {
    const seg = this.segments.get(tuId)!;
    const box = document.createElement("div");
    box.style.position = "absolute";
    box.style.border = `2px solid ${scoreColor(seg.latest_score)}`;
    box.style.borderRadius = "3px";
    box.style.boxSizing = "border-box";
    box.style.pointerEvents = "auto";
    box.style.cursor = "pointer";
    box.style.transition = "background-color 120ms ease";
    box.title = seg.latest_score !== null ? `Quality: ${seg.latest_score}` : "Not yet scored";
    box.addEventListener("mouseenter", () => { box.style.backgroundColor = `${scoreColor(seg.latest_score)}22`; });
    box.addEventListener("mouseleave", () => { box.style.backgroundColor = "transparent"; });
    box.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.transport.send({ type: "tu:selected", tuId });
    });
    this.layer.appendChild(box);
    this.boxes.set(tuId, box);
    this.positionBox(el, box);
  }

  private positionBox(el: HTMLElement, box: HTMLDivElement): void {
    const rect = el.getBoundingClientRect();
    box.style.top = `${rect.top + window.scrollY}px`;
    box.style.left = `${rect.left + window.scrollX}px`;
    box.style.width = `${rect.width}px`;
    box.style.height = `${rect.height}px`;
  }

  private scheduleReposition = (): void => {
    if (this.rafId !== null) return;
    this.rafId = requestAnimationFrame(() => {
      this.rafId = null;
      for (const [tuId, box] of this.boxes) {
        const el = document.querySelector<HTMLElement>(`[data-tu-id="${CSS.escape(tuId)}"]`);
        if (el) this.positionBox(el, box);
      }
    });
  };

  private handleShellMessage = (msg: ShellToOverlayMessage): void => {
    if (!msg || typeof msg !== "object") return;

    if (msg.type === "tu:preview") {
      const el = document.querySelector<HTMLElement>(`[data-tu-id="${CSS.escape(msg.tuId)}"]`);
      if (el) el.textContent = msg.text;
      return;
    }
    if (msg.type === "tu:scrollTo") {
      const box = this.boxes.get(msg.tuId);
      const el = document.querySelector<HTMLElement>(`[data-tu-id="${CSS.escape(msg.tuId)}"]`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        if (box) this.flash(box);
      }
    }
  };

  private flash(box: HTMLDivElement): void {
    const original = box.style.boxShadow;
    box.style.boxShadow = `0 0 0 4px ${scoreColor(null)}55`;
    setTimeout(() => { box.style.boxShadow = original; }, 900);
  }
}

export function initReviewOverlay(config: ReviewOverlayConfig = {}): void {
  const active = config.active ?? isReviewMode();
  if (!active) {
    console.log("[review-sdk] not in review mode (no ?__review=1 in URL) — overlay inactive");
    return;
  }
  console.log("[review-sdk] initializing, apiBase =", config.apiBase ?? "/api/v1");
  const overlay = new ReviewOverlay(config);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void overlay.start());
  } else {
    void overlay.start();
  }
}
