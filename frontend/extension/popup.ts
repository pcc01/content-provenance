// popup.ts — plain TypeScript, no framework: pick a source/target
// language, click "Start reviewing this tab" to inject the harvest
// content script into whichever tab was active when the popup opened, and
// a small page-notes read/add panel (same REST endpoints ReviewPage's
// PageNotes.tsx uses) for jotting observations without switching to the
// Review Shell tab at all.

const API_BASE = "http://localhost:8001/api/v1";

function el<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

async function currentTab(): Promise<chrome.tabs.Tab | undefined> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function targetLanguage(): string {
  return el<HTMLInputElement>("targetLanguage").value.trim() || "fr-FR";
}

function sourceLanguage(): string {
  return el<HTMLInputElement>("sourceLanguage").value.trim() || "en-US";
}

async function startReview(): Promise<void> {
  const status = el<HTMLDivElement>("status");
  const tab = await currentTab();
  if (!tab?.id) {
    status.textContent = "No active tab found.";
    return;
  }
  await chrome.storage.local.set({ targetLanguage: targetLanguage(), sourceLanguage: sourceLanguage() });

  status.textContent = "Starting…";
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["review-sdk/overlay.js", "review-sdk/harvest.js", "harvest-content-script.js"],
    });
    chrome.runtime.sendMessage({ type: "start-review", tabId: tab.id });
    status.textContent = "Reviewing this tab — open the Review Shell's Live tab to see segments.";
  } catch (e) {
    status.textContent = `Failed to start: ${e instanceof Error ? e.message : String(e)}`;
  }
}

async function loadNotes(): Promise<void> {
  const tab = await currentTab();
  if (!tab?.url) return;
  const list = el<HTMLUListElement>("notesList");
  try {
    const res = await fetch(`${API_BASE}/pages/notes?${new URLSearchParams({ url: tab.url, target_language: targetLanguage() })}`);
    if (!res.ok) return;
    const notes: { id: string; author: string; body: string }[] = await res.json();
    list.innerHTML = "";
    for (const n of notes) {
      const li = document.createElement("li");
      li.textContent = `${n.author}: ${n.body}`;
      list.appendChild(li);
    }
  } catch {
    // API not reachable — leave the list as-is rather than erroring the popup.
  }
}

async function addNote(): Promise<void> {
  const tab = await currentTab();
  const bodyInput = el<HTMLInputElement>("noteBody");
  const body = bodyInput.value.trim();
  if (!tab?.url || !body) return;

  const addButton = el<HTMLButtonElement>("addNoteButton");
  addButton.disabled = true;
  addButton.textContent = "Saving…";
  try {
    const res = await fetch(`${API_BASE}/pages/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: tab.url, target_language: targetLanguage(), author: "reviewer@example.com", body }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    bodyInput.value = "";
    addButton.textContent = "Saved ✓";
    await loadNotes();
  } catch (e) {
    addButton.textContent = "Failed";
    console.error("[review-extension] add note failed", e);
  } finally {
    setTimeout(() => { addButton.disabled = false; addButton.textContent = "Add"; }, 1200);
  }
}

el<HTMLButtonElement>("startButton").addEventListener("click", () => void startReview());
el<HTMLButtonElement>("addNoteButton").addEventListener("click", () => void addNote());
void loadNotes();
