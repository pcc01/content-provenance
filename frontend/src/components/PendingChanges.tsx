import { useEffect, useState } from "react";
import { api, type PendingChange } from "../api/client";

interface Props {
  url: string;
  targetLanguage: string;
  ready: boolean;
  onApplied: () => void;
}

// Phase 10's editor view: every unapproved proposal on the current page,
// with individual and bulk approve actions. In-page, the same segments
// get a distinct dashed-purple overlay box (see overlay.ts's
// PENDING_COLOR) — this panel is the worklist for the same state.
export function PendingChanges({ url, targetLanguage, ready, onApplied }: Props) {
  const [pending, setPending] = useState<PendingChange[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [actor, setActor] = useState("editor@example.com");

  function reload() {
    if (!ready) return;
    api.getPendingChanges(url, targetLanguage)
      .then((r) => setPending(r.pending))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    setPending(null);
    setError(null);
    reload();
  }, [url, targetLanguage, ready]);

  async function approve(itemIds: string[]) {
    setBusyIds((s) => new Set([...s, ...itemIds]));
    setError(null);
    try {
      const { results } = await api.bulkApproveItems(itemIds, actor);
      const failed = results.filter((r) => !r.ok);
      if (failed.length > 0) setError(`${failed.length} item(s) failed to approve.`);
      reload();
      onApplied();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyIds((s) => {
        const next = new Set(s);
        itemIds.forEach((id) => next.delete(id));
        return next;
      });
    }
  }

  if (!ready) return null;
  if (pending === null) return <div style={{ fontSize: 12, color: "#9ca3af" }}>Loading pending changes…</div>;
  if (pending.length === 0) return null;

  return (
    <div style={{ borderTop: "1px solid #e5e7eb", paddingTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 12, fontWeight: 600 }}>Pending changes ({pending.length})</div>
        <button
          onClick={() => approve(pending.map((p) => p.item_id))}
          disabled={busyIds.size > 0}
          style={{ fontSize: 11, cursor: "pointer" }}
        >
          Approve all
        </button>
      </div>
      <input
        value={actor} onChange={(e) => setActor(e.target.value)}
        placeholder="Your name/email" style={{ fontSize: 11, padding: 4 }}
      />
      {error && (
        <div style={{ fontSize: 11, color: "#b91c1c", background: "#fef2f2", padding: 6, borderRadius: 4 }}>
          {error}
        </div>
      )}
      {pending.map((p) => (
        <div key={p.item_id} style={{
          padding: 6, borderRadius: 4, background: "#faf5ff", border: "1px dashed #c4b5fd", fontSize: 11,
        }}>
          <div style={{ color: "#6b7280", marginBottom: 2 }}>{p.source_text}</div>
          <div style={{ color: "#b91c1c", textDecoration: "line-through" }}>{p.current_text}</div>
          <div style={{ color: "#15803d", marginBottom: 4 }}>{p.proposed_text}</div>
          <button
            onClick={() => approve([p.item_id])}
            disabled={busyIds.has(p.item_id)}
            style={{ fontSize: 11, cursor: "pointer" }}
          >
            {busyIds.has(p.item_id) ? "Approving…" : "Approve"}
          </button>
        </div>
      ))}
    </div>
  );
}
