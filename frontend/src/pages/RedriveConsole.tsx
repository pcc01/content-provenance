import { useEffect, useState } from "react";
import {
  api, EVALUATE_PROVIDERS, TRANSLATE_PROVIDERS,
  type EvaluateResult, type RedrivePreview, type RedriveRun, type StyleGuide,
} from "../api/client";
import { PageIntro } from "../components/PageIntro";
import { QualityBadge } from "../components/QualityBadge";

export function RedriveConsole() {
  const [targetLanguage, setTargetLanguage] = useState("");
  const [threshold, setThreshold] = useState(80);
  // Phase 13 — a second, independent threshold axis: a unit redrives if
  // EITHER quality or style falls below its own threshold. Off (undefined)
  // by default — style is scored and recorded either way, but only counts
  // toward a redrive decision once a style guide is actually selected here.
  const [styleEnabled, setStyleEnabled] = useState(false);
  const [styleThreshold, setStyleThreshold] = useState(70);
  const [styleGuideId, setStyleGuideId] = useState("");
  const [guides, setGuides] = useState<StyleGuide[]>([]);
  const [requireApproval, setRequireApproval] = useState(false);
  // Phase 16 — independently selectable "evaluate" (scoring_provider) and
  // "retranslate" (redrive_provider) models; "" = each falls back to its
  // own app default. Deliberately two separate dropdowns, not one — you
  // can e.g. evaluate with Claude but redrive with a cheaper/local model.
  const [scoringProvider, setScoringProvider] = useState("");
  const [redriveProvider, setRedriveProvider] = useState("");
  const [preview, setPreview] = useState<RedrivePreview | null>(null);
  const [run, setRun] = useState<RedriveRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [actor, setActor] = useState("reviewer@example.com");

  // Ad-hoc per-unit evaluate — independent of the threshold/preview/run
  // flow above, for "just score this one unit with this one model" (the
  // standalone POST /quality/evaluate endpoint).
  const [evalUnitId, setEvalUnitId] = useState("");
  const [evalProvider, setEvalProvider] = useState("");
  const [evalResult, setEvalResult] = useState<EvaluateResult | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => { api.listStyleGuides().then(setGuides); }, []);

  async function doPreview() {
    setBusy(true);
    try {
      setPreview(await api.previewRedrive({
        threshold, target_language: targetLanguage || undefined,
        style_threshold: styleEnabled ? styleThreshold : undefined,
        style_guide_id: styleEnabled ? (styleGuideId || undefined) : undefined,
        scoring_provider: scoringProvider || undefined,
      }));
    } finally {
      setBusy(false);
    }
  }

  async function doRun() {
    setBusy(true);
    try {
      const scope = targetLanguage ? { target_language: targetLanguage } : {};
      const result = await api.createRedriveRun({
        threshold, scope, require_human_approval: requireApproval,
        style_threshold: styleEnabled ? styleThreshold : undefined,
        style_guide_id: styleEnabled ? (styleGuideId || undefined) : undefined,
        scoring_provider: scoringProvider || undefined,
        redrive_provider: redriveProvider || undefined,
      });
      setRun(result);
    } finally {
      setBusy(false);
    }
  }

  async function doEvaluate() {
    if (!evalUnitId.trim()) return;
    setEvaluating(true);
    try {
      setEvalResult(await api.evaluateUnit(evalUnitId.trim(), evalProvider || undefined));
    } finally {
      setEvaluating(false);
    }
  }

  async function approve(itemId: string) {
    if (!run) return;
    await api.approveRedriveItem(run.id, itemId, actor);
    setRun(await api.getRedriveRun(run.id));
  }

  async function reject(itemId: string) {
    if (!run) return;
    await api.rejectRedriveItem(run.id, itemId, actor, "declined in review console");
    setRun(await api.getRedriveRun(run.id));
  }

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <PageIntro
        title="Redrive Console"
        requires="a threshold and target language are already set below — click 'Preview' to see what would redrive without spending anything, or 'Run redrive' to actually do it."
      >
        Score everything in scope, then redrive whatever falls below the threshold. With human-in-the-loop
        enabled, redrives are proposed but not applied until approved below.
      </PageIntro>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
        <label style={{ fontSize: 13 }}>
          Target language (blank = all)
          <input value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)}
                 placeholder="fr-FR" style={{ display: "block", width: 200, marginTop: 4, padding: 4 }} />
        </label>
        <label style={{ fontSize: 13 }}>
          Threshold: <strong>{threshold}</strong>
          <input type="range" min={0} max={100} value={threshold}
                 onChange={(e) => setThreshold(Number(e.target.value))} style={{ display: "block", width: 300 }} />
        </label>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={styleEnabled} onChange={(e) => setStyleEnabled(e.target.checked)} />
          Also redrive on style/voice score (Phase 13)
        </label>
        {styleEnabled && (
          <div style={{ paddingLeft: 24, display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={{ fontSize: 13 }}>
              Style guide
              <select value={styleGuideId} onChange={(e) => setStyleGuideId(e.target.value)}
                      style={{ display: "block", padding: 4, marginTop: 4, minWidth: 200 }}>
                <option value="">Any / no specific guide</option>
                {guides.map((g) => <option key={g.id} value={g.id}>{g.name} v{g.version}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 13 }}>
              Style threshold: <strong>{styleThreshold}</strong>
              <input type="range" min={0} max={100} value={styleThreshold}
                     onChange={(e) => setStyleThreshold(Number(e.target.value))} style={{ display: "block", width: 300 }} />
            </label>
          </div>
        )}
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={requireApproval} onChange={(e) => setRequireApproval(e.target.checked)} />
          Require human approval before applying redrives
        </label>
        <div style={{ display: "flex", gap: 10 }}>
          <label style={{ fontSize: 13 }}>
            Evaluate with
            <select value={scoringProvider} onChange={(e) => setScoringProvider(e.target.value)}
                    style={{ display: "block", padding: 4, marginTop: 4, minWidth: 190 }}>
              {EVALUATE_PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </label>
          <label style={{ fontSize: 13 }}>
            Retranslate with
            <select value={redriveProvider} onChange={(e) => setRedriveProvider(e.target.value)}
                    style={{ display: "block", padding: 4, marginTop: 4, minWidth: 190 }}>
              {TRANSLATE_PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </label>
        </div>
        <label style={{ fontSize: 13 }}>
          Approving/rejecting as
          <input value={actor} onChange={(e) => setActor(e.target.value)}
                 style={{ display: "block", width: 240, marginTop: 4, padding: 4 }} />
        </label>

        <div style={{ display: "flex", gap: 8 }}>
          <button disabled={busy} onClick={doPreview} style={{ padding: "6px 14px", cursor: "pointer" }}>
            Preview
          </button>
          <button disabled={busy} onClick={doRun} style={{ padding: "6px 14px", cursor: "pointer" }}>
            Run redrive
          </button>
        </div>
      </div>

      {preview && (
        <div style={{ marginBottom: 20, padding: 12, background: "#f9fafb", borderRadius: 6, fontSize: 13 }}>
          <div>{preview.scope_count} unit(s) in scope</div>
          <div><strong>{preview.below_threshold}</strong> would redrive on quality (threshold {threshold})</div>
          {styleEnabled && preview.below_style_threshold !== undefined && (
            <div><strong>{preview.below_style_threshold}</strong> would redrive on style (threshold {styleThreshold})</div>
          )}
          <div>~{preview.estimated_source_chars.toLocaleString()} source characters via {preview.redrive_provider}</div>
        </div>
      )}

      <div style={{ marginBottom: 24, padding: 12, background: "#f9fafb", borderRadius: 6 }}>
        <h3 style={{ marginTop: 0, fontSize: 15 }}>Evaluate a single unit</h3>
        <p style={{ color: "#6b7280", fontSize: 13, marginTop: 0 }}>
          Score one unit on demand with a chosen model — independent of the threshold run above.
          Requires a unit id (copy one from the Review tab, or from a run's results table below
          once you've run a redrive) — nothing runs without one.
        </p>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13 }}>
            Unit id
            <input value={evalUnitId} onChange={(e) => setEvalUnitId(e.target.value)}
                   placeholder="unit id" style={{ display: "block", width: 260, marginTop: 4, padding: 4 }} />
          </label>
          <label style={{ fontSize: 13 }}>
            Evaluate with
            <select value={evalProvider} onChange={(e) => setEvalProvider(e.target.value)}
                    style={{ display: "block", padding: 4, marginTop: 4, minWidth: 190 }}>
              {EVALUATE_PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </label>
          <button disabled={evaluating || !evalUnitId.trim()} onClick={doEvaluate} style={{ padding: "6px 14px", cursor: "pointer" }}>
            {evaluating ? "Scoring…" : "Evaluate"}
          </button>
        </div>
        {evalResult && (
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <QualityBadge score={evalResult.score} hardFail={evalResult.hard_fail} />
              <span style={{ color: "#6b7280" }}>via {evalResult.scorer}</span>
              {evalResult.needs_review && <span style={{ color: "#92400e" }}>needs review</span>}
            </div>
            {evalResult.reasons.length > 0 && (
              <div style={{ color: "#6b7280" }}>{evalResult.reasons.join(", ")}</div>
            )}
          </div>
        )}
      </div>

      {run && (
        <div>
          <h3>Run {run.id.slice(0, 8)} — {run.status}</h3>
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 8 }}>
            {Object.entries(run.summary).map(([k, v]) => `${k}: ${v}`).join(" · ")}
          </div>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                <th>Unit</th><th>Before</th><th>After</th><th>Outcome</th><th></th>
              </tr>
            </thead>
            <tbody>
              {run.items.map((item) => (
                <tr key={item.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>{item.unit_id.slice(0, 8)}</td>
                  <td><QualityBadge score={item.before_score} /></td>
                  <td><QualityBadge score={item.after_score} /></td>
                  <td>{item.outcome}</td>
                  <td>
                    {item.outcome === "pending_approval" && (
                      <div style={{ display: "flex", gap: 4 }}>
                        <button onClick={() => approve(item.id)} style={{ cursor: "pointer", fontSize: 11 }}>Approve</button>
                        <button onClick={() => reject(item.id)} style={{ cursor: "pointer", fontSize: 11 }}>Reject</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
