// Shared DOM harvesting/rewriting logic — used by BOTH Phase 8's Playwright
// fetch path (compiled to dist/harvest.js, evaluated in a headless page via
// app/core/page_fetch.py) and Phase 10's browser extension content script
// (imported directly). One implementation so the two can't silently drift
// apart — this is the exact logic that used to live as Python string
// literals (_HARVEST_JS/_REWRITE_JS) inside page_fetch.py.

export interface HarvestedItem {
  idx: number;
  domPath: string;
  text: string;
}

function isHarvestable(el: Element): el is HTMLElement {
  if (!(el instanceof HTMLElement)) return false;
  const skip = ["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "IFRAME", "SVG"];
  if (skip.includes(el.tagName)) return false;
  if (el.children.length > 0) return false;
  const text = (el.textContent || "").replace(/\s+/g, " ").trim();
  if (text.length < 2) return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return false;
  return true;
}

function domPath(el: Element): string {
  const path: string[] = [];
  let node: Element | null = el;
  while (node && node.nodeType === 1 && node.tagName !== "HTML") {
    let selector = node.tagName;
    if (node.parentElement) {
      const siblings = Array.from(node.parentElement.children).filter((s) => s.tagName === node!.tagName);
      if (siblings.length > 1) selector += ":nth-of-type(" + (siblings.indexOf(node) + 1) + ")";
    }
    path.unshift(selector);
    node = node.parentElement;
  }
  return path.join(">");
}

export function harvest(): HarvestedItem[] {
  const results: HarvestedItem[] = [];
  let idx = 0;
  document.querySelectorAll("*").forEach((el) => {
    if (!isHarvestable(el)) return;
    const text = (el.textContent || "").replace(/\s+/g, " ").trim();
    el.setAttribute("data-tu-harvest-idx", String(idx));
    results.push({ idx, domPath: domPath(el), text });
    idx += 1;
  });
  return results;
}

export interface RewriteEntry {
  tuId: string;
  targetText: string;
}

// swapText=true rewrites each matched element's text to targetText and
// resolves asset URLs to absolute (Phase 8's fetch+rewrite pages, served
// from a different origin than the original). swapText=false only tags
// data-tu-id and leaves everything else alone — Phase 10's live-tab mode,
// where the page IS the real page (its own assets already resolve
// correctly) and swapping a live page's actual text out from under a user
// who might be using the real site would be the wrong default.
export function rewrite(mapping: Record<string, RewriteEntry>, swapText: boolean): void {
  for (const [idx, entry] of Object.entries(mapping)) {
    const el = document.querySelector(`[data-tu-harvest-idx="${idx}"]`);
    if (!el) continue;
    el.setAttribute("data-tu-id", entry.tuId);
    if (swapText) el.textContent = entry.targetText;
  }
  document.querySelectorAll("[data-tu-harvest-idx]").forEach((el) => el.removeAttribute("data-tu-harvest-idx"));

  if (!swapText) return;

  // srcset is dropped rather than rewritten — its multi-URL/descriptor
  // syntax isn't worth the parsing complexity for a v1; plain src still resolves.
  const urlAttrs: [string, string][] = [
    ["img", "src"], ["img", "srcset"], ["source", "src"], ["video", "src"],
    ["audio", "src"], ["script", "src"], ["link", "href"], ["a", "href"],
  ];
  for (const [tag, attr] of urlAttrs) {
    document.querySelectorAll(`${tag}[${attr}]`).forEach((el) => {
      if (attr === "srcset") { el.removeAttribute("srcset"); return; }
      try {
        el.setAttribute(attr, (el as unknown as Record<string, string>)[attr]);
      } catch {
        /* ignore unresolvable */
      }
    });
  }
}
