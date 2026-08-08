import { useEffect, useState } from "react";
import { api, type GlossaryTerm, type StyleGuide, type StyleGuideRule } from "../api/client";

// Phase 13 — define the brand voice/terminology rules the graph-based
// retrieval layer feeds to AI translation and scores translations against.
// This is the first stop in the Content Creation workflow: nothing else in
// this segment has anything useful to check against until a guide exists.
export function StyleGuidesPage() {
  const [guides, setGuides] = useState<StyleGuide[]>([]);
  const [selected, setSelected] = useState<StyleGuide | null>(null);
  const [rules, setRules] = useState<StyleGuideRule[]>([]);
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [newGuideName, setNewGuideName] = useState("");
  const [newGuideLocale, setNewGuideLocale] = useState("");
  const [newGuideVoice, setNewGuideVoice] = useState("");

  const [newRuleType, setNewRuleType] = useState<StyleGuideRule["rule_type"]>("tone");
  const [newRuleText, setNewRuleText] = useState("");
  const [newRuleLocale, setNewRuleLocale] = useState("");

  const [newTermSource, setNewTermSource] = useState("");
  const [newTermTarget, setNewTermTarget] = useState("");
  const [newTermDNT, setNewTermDNT] = useState(false);

  async function refreshGuides() {
    setGuides(await api.listStyleGuides());
  }

  useEffect(() => { refreshGuides(); }, []);

  async function selectGuide(guide: StyleGuide) {
    setSelected(guide);
    setError(null);
    try {
      const [r, t] = await Promise.all([
        api.listStyleGuideRules(guide.id),
        api.listGlossaryTerms({ style_guide_id: guide.id }),
      ]);
      setRules(r);
      setTerms(t);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function createGuide() {
    if (!newGuideName.trim()) return;
    setError(null);
    try {
      const guide = await api.createStyleGuide({
        name: newGuideName, locale: newGuideLocale || undefined, voice_description: newGuideVoice || undefined,
      });
      setNewGuideName(""); setNewGuideLocale(""); setNewGuideVoice("");
      await refreshGuides();
      await selectGuide(guide);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function addRule() {
    if (!selected || !newRuleText.trim()) return;
    setError(null);
    try {
      await api.createStyleGuideRule(selected.id, {
        rule_type: newRuleType, rule_text: newRuleText, applies_to_locale: newRuleLocale || undefined,
      });
      setNewRuleText(""); setNewRuleLocale("");
      setRules(await api.listStyleGuideRules(selected.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function addTerm() {
    if (!selected || !newTermSource.trim()) return;
    setError(null);
    try {
      await api.createGlossaryTerm({
        source_term: newTermSource, target_term: newTermDNT ? undefined : (newTermTarget || undefined),
        do_not_translate: newTermDNT, style_guide_id: selected.id,
      });
      setNewTermSource(""); setNewTermTarget(""); setNewTermDNT(false);
      setTerms(await api.listGlossaryTerms({ style_guide_id: selected.id }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 960 }}>
      <h2 style={{ marginTop: 0 }}>Style Guides &amp; Glossary</h2>
      <p style={{ color: "#6b7280" }}>
        Brand voice/tone rules and terminology retrieved automatically before every AI translation
        (see the Retrieval Preview tool) and scored against on every redrive.
      </p>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 24 }}>
        <div style={{ width: 260, flexShrink: 0 }}>
          <h3 style={{ fontSize: 14 }}>Guides</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 16 }}>
            {guides.map((g) => (
              <button key={g.id} onClick={() => selectGuide(g)}
                style={{
                  textAlign: "left", padding: "6px 10px", borderRadius: 6, cursor: "pointer",
                  border: "1px solid #e5e7eb", background: selected?.id === g.id ? "#f3f4f6" : "white",
                  fontWeight: selected?.id === g.id ? 600 : 400, fontSize: 13,
                }}
              >
                {g.name} <span style={{ color: "#9ca3af" }}>v{g.version}</span>
                {g.locale && <span style={{ color: "#9ca3af" }}> · {g.locale}</span>}
              </button>
            ))}
            {guides.length === 0 && <div style={{ fontSize: 13, color: "#9ca3af" }}>No style guides yet.</div>}
          </div>

          <h3 style={{ fontSize: 14 }}>New guide</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input placeholder="Name" value={newGuideName} onChange={(e) => setNewGuideName(e.target.value)}
                   style={{ padding: 4, fontSize: 13 }} />
            <input placeholder="Locale (blank = all)" value={newGuideLocale} onChange={(e) => setNewGuideLocale(e.target.value)}
                   style={{ padding: 4, fontSize: 13 }} />
            <textarea placeholder="Voice description" value={newGuideVoice} onChange={(e) => setNewGuideVoice(e.target.value)}
                      rows={3} style={{ padding: 4, fontSize: 13 }} />
            <button onClick={createGuide} style={{ padding: "6px 10px", cursor: "pointer" }}>Create guide</button>
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!selected ? (
            <div style={{ color: "#9ca3af", fontSize: 13 }}>Select or create a guide to manage its rules and glossary.</div>
          ) : (
            <>
              <h3 style={{ marginTop: 0 }}>{selected.name}</h3>
              {selected.voice_description && <p style={{ color: "#374151", fontSize: 13 }}>{selected.voice_description}</p>}

              <h4 style={{ fontSize: 13, marginBottom: 4 }}>Rules</h4>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse", marginBottom: 12 }}>
                <tbody>
                  {rules.map((r) => (
                    <tr key={r.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "4px 6px", color: "#6b7280", width: 90 }}>{r.rule_type}</td>
                      <td style={{ padding: "4px 6px" }}>{r.rule_text}</td>
                      <td style={{ padding: "4px 6px", color: "#9ca3af", width: 70 }}>{r.applies_to_locale ?? "all"}</td>
                    </tr>
                  ))}
                  {rules.length === 0 && <tr><td style={{ color: "#9ca3af", fontSize: 12 }}>No rules yet.</td></tr>}
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
                <select value={newRuleType} onChange={(e) => setNewRuleType(e.target.value as StyleGuideRule["rule_type"])}
                        style={{ padding: 4, fontSize: 12 }}>
                  <option value="tone">tone</option>
                  <option value="voice">voice</option>
                  <option value="terminology">terminology</option>
                  <option value="formatting">formatting</option>
                </select>
                <input placeholder="Rule text" value={newRuleText} onChange={(e) => setNewRuleText(e.target.value)}
                       style={{ flex: 1, padding: 4, fontSize: 12 }} />
                <input placeholder="Locale" value={newRuleLocale} onChange={(e) => setNewRuleLocale(e.target.value)}
                       style={{ width: 80, padding: 4, fontSize: 12 }} />
                <button onClick={addRule} style={{ padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>Add</button>
              </div>

              <h4 style={{ fontSize: 13, marginBottom: 4 }}>Glossary</h4>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse", marginBottom: 12 }}>
                <tbody>
                  {terms.map((t) => (
                    <tr key={t.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "4px 6px" }}>{t.source_term}</td>
                      <td style={{ padding: "4px 6px", color: "#6b7280" }}>
                        {t.do_not_translate ? "(do not translate)" : `→ ${t.target_term ?? "?"}`}
                      </td>
                    </tr>
                  ))}
                  {terms.length === 0 && <tr><td style={{ color: "#9ca3af", fontSize: 12 }}>No glossary terms yet.</td></tr>}
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input placeholder="Source term" value={newTermSource} onChange={(e) => setNewTermSource(e.target.value)}
                       style={{ padding: 4, fontSize: 12 }} />
                <input placeholder="Target term" value={newTermTarget} disabled={newTermDNT}
                       onChange={(e) => setNewTermTarget(e.target.value)} style={{ padding: 4, fontSize: 12 }} />
                <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}>
                  <input type="checkbox" checked={newTermDNT} onChange={(e) => setNewTermDNT(e.target.checked)} />
                  Do not translate
                </label>
                <button onClick={addTerm} style={{ padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>Add</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
