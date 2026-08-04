import { useEffect, useState } from "react";
import { api, type ReviewNote } from "../api/client";

// Phase 10: notes that attach to a whole page (url+target_language)
// instead of one segment — for observations from a review session that
// don't map to a single unit ("use formal register throughout this
// page"). Same shape as NotesThread.tsx's per-segment notes, just a
// different key. Used both in ReviewPage's fetch-mode sidebar and the
// browser extension's popup — same component, two hosts.
export function PageNotes({ url, targetLanguage }: { url: string; targetLanguage: string }) {
  const [notes, setNotes] = useState<ReviewNote[]>([]);
  const [author, setAuthor] = useState("reviewer@example.com");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  const reload = () => api.getPageNotes(url, targetLanguage).then(setNotes).finally(() => setLoading(false));

  useEffect(() => { setLoading(true); reload(); }, [url, targetLanguage]);

  async function submit() {
    if (!body.trim()) return;
    setSaveState("saving");
    setSaveError(null);
    try {
      await api.addPageNote(url, targetLanguage, author, body.trim());
      setBody("");
      await reload();
      setSaveState("saved");
      setTimeout(() => setSaveState((s) => (s === "saved" ? "idle" : s)), 1500);
    } catch (e) {
      setSaveState("error");
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  }

  async function toggleResolved(note: ReviewNote) {
    try {
      await api.resolvePageNote(note.id, !note.resolved);
      await reload();
    } catch (e) {
      setSaveState("error");
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  }

  if (loading) return <div style={{ fontSize: 12, color: "#9ca3af" }}>Loading page notes…</div>;

  return (
    <div style={{ borderTop: "1px solid #e5e7eb", paddingTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 600 }}>Page notes ({notes.length})</div>
      {notes.map((n) => (
        <div key={n.id} style={{
          padding: 6, borderRadius: 4, background: n.resolved ? "#f0fdf4" : "#f9fafb",
          border: "1px solid #e5e7eb", fontSize: 12,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#6b7280", fontSize: 11 }}>
            <span>{n.author} · {new Date(n.created_at).toLocaleString()}</span>
            <button onClick={() => toggleResolved(n)} style={{ fontSize: 11, cursor: "pointer" }}>
              {n.resolved ? "Reopen" : "Resolve"}
            </button>
          </div>
          <div style={{ marginTop: 2 }}>{n.body}</div>
        </div>
      ))}

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <input
          value={author} onChange={(e) => setAuthor(e.target.value)}
          placeholder="Your name/email" style={{ fontSize: 11, padding: 4 }}
        />
        <div style={{ display: "flex", gap: 4 }}>
          <input
            value={body} onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            placeholder="Note a challenge or strategy for this page…"
            style={{ flex: 1, fontSize: 12, padding: 4 }}
          />
          <button onClick={submit} disabled={saveState === "saving"} style={{ fontSize: 12, cursor: "pointer", minWidth: 50 }}>
            {saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved ✓" : "Add"}
          </button>
        </div>
        {saveState === "error" && (
          <div style={{ fontSize: 11, color: "#b91c1c", background: "#fef2f2", padding: 6, borderRadius: 4 }}>
            Failed to save: {saveError}
          </div>
        )}
      </div>
    </div>
  );
}
