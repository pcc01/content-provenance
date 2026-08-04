import { useEffect, useState } from "react";
import { api, type ReviewNote } from "../api/client";

export function NotesThread({ unitId }: { unitId: string }) {
  const [notes, setNotes] = useState<ReviewNote[]>([]);
  const [author, setAuthor] = useState("reviewer@example.com");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = () => api.listNotes(unitId).then(setNotes).finally(() => setLoading(false));

  useEffect(() => { setLoading(true); reload(); }, [unitId]);

  async function submit() {
    if (!body.trim()) return;
    await api.addNote(unitId, author, body.trim());
    setBody("");
    reload();
  }

  async function toggleResolved(note: ReviewNote) {
    await api.resolveNote(unitId, note.id, !note.resolved);
    reload();
  }

  if (loading) return <p style={{ color: "#6b7280" }}>Loading notes…</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {notes.length === 0 && <p style={{ color: "#6b7280", fontSize: 13 }}>No notes yet.</p>}
      {notes.map((n) => (
        <div key={n.id} style={{
          padding: 8, borderRadius: 6, background: n.resolved ? "#f0fdf4" : "#f9fafb",
          border: "1px solid #e5e7eb", marginLeft: n.parent_id ? 16 : 0,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#6b7280" }}>
            <span>{n.author} · {new Date(n.created_at).toLocaleString()}</span>
            <button onClick={() => toggleResolved(n)} style={{ fontSize: 11, cursor: "pointer" }}>
              {n.resolved ? "Reopen" : "Resolve"}
            </button>
          </div>
          <div style={{ fontSize: 14, marginTop: 4 }}>{n.body}</div>
        </div>
      ))}

      <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
        <input
          value={author} onChange={(e) => setAuthor(e.target.value)}
          placeholder="Your name/email" style={{ width: 140, fontSize: 12, padding: 4 }}
        />
        <input
          value={body} onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="Add a note…" style={{ flex: 1, fontSize: 13, padding: 4 }}
        />
        <button onClick={submit} style={{ fontSize: 12, cursor: "pointer" }}>Add</button>
      </div>
    </div>
  );
}
