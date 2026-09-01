import { useEffect, useMemo, useState } from "react";
import {
  ACTIONABLE_BUCKETS, api, BUCKET_COLOR, BUCKET_LABEL, EVALUATE_PROVIDERS,
  MPROMETHEUS_REFERENCE_MODES, qualityReportJsonUrl, qualityReportPdfUrl, TRANSLATE_PROVIDERS,
  type EvaluateResult, type QualityBucket, type QualityReport, type QualityReportItem,
  type RecommendedAction, type RedriveRouting, type RedriveRun, type RoutingTarget, type StyleGuide,
} from "../api/client";
import { BarChart } from "../components/BarChart";
import { LocaleSelect } from "../components/LocaleSelect";
import { ModelPicker } from "../components/ModelPicker";
import { PageIntro } from "../components/PageIntro";
import { QualityBadge } from "../components/QualityBadge";

type Step = "evaluate" | "report" | "redrive";
type BucketRoute = {
  action: RecommendedAction | "";
  override: boolean; // false = inherit the pipeline retranslate engine
  provider: string;
  model: string;
  sendToCrowdin: boolean; // action=human only: review in Crowdin, not the in-app queue
};

const STEP_TITLE: Record<Step, string> = {
  evaluate: "1 · Evaluate",
  report: "2 · Quality report",
  redrive: "3 · Redrive",
};

const ACTION_OPTIONS: { value: RecommendedAction | ""; label: string }[] = [
  { value: "", label: "Use the report's recommendation" },
  { value: "none", label: "Leave as-is" },
  { value: "human", label: "Route to a human reviewer" },
  { value: "mt", label: "Retranslate with an MT engine" },
];

function emptyBucketRoutes(): Record<string, BucketRoute> {
  return Object.fromEntries(
    ACTIONABLE_BUCKETS.map((b) => [b, { action: "", override: false, provider: "", model: "", sendToCrowdin: false } as BucketRoute]),
  );
}

function providerLabel(list: { value: string; label: string }[], value: string): string {
  return list.find((p) => p.value === value)?.label ?? value;
}

// Client-side "what if" — recompute a unit's bucket at a different quality
// threshold, mirroring RedriveEngine._classify_bucket's precedence.
function projectBucket(it: QualityReportItem, t: number, styleThreshold: number | null): QualityBucket {
  if (it.needs_review || it.before_score === null) return "needs_review";
  if (it.hard_fail) return "hard_fail";
  if (it.before_score < t) return "below_quality";
  if (styleThreshold !== null && it.style_score !== null && it.style_score < styleThreshold) return "below_style";
  return "pass";
}

function commercialTag(safe: boolean | null): { text: string; color: string } {
  if (safe === true) return { text: "safe", color: "#6b7280" };
  if (safe === false) return { text: "NON-COMM", color: "#e5484d" };
  return { text: "unknown", color: "#92400e" };
}

export function RedriveConsole() {
  const [step, setStep] = useState<Step>("evaluate");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Pipeline: models for each step + approval gates ─────────────────
  // One place to say "this model evaluates, this model retranslates" —
  // the per-bucket pickers in step 3 inherit the retranslate engine
  // unless a bucket explicitly overrides it.
  const [scoringProvider, setScoringProvider] = useState("");
  const [scoringModel, setScoringModel] = useState("");
  const [referenceMode, setReferenceMode] = useState("auto");
  const [redriveProvider, setRedriveProvider] = useState("");
  const [redriveModel, setRedriveModel] = useState("");
  const [gatePauseOnReport, setGatePauseOnReport] = useState(true);
  const [gateApprovePlan, setGateApprovePlan] = useState(false);
  const [secondReview, setSecondReview] = useState(false);
  const [planApproved, setPlanApproved] = useState(false);

  // ── Step 1: evaluate inputs ─────────────────────────────────────────
  const [targetLanguage, setTargetLanguage] = useState("");
  const [threshold, setThreshold] = useState(80);
  const [styleEnabled, setStyleEnabled] = useState(false);
  const [styleThreshold, setStyleThreshold] = useState(70);
  const [styleGuideId, setStyleGuideId] = useState("");
  const [guides, setGuides] = useState<StyleGuide[]>([]);
  const [triggeredBy, setTriggeredBy] = useState("reviewer@example.com");
  const [recent, setRecent] = useState<QualityReport[]>([]);

  // ── Step 2: report ──────────────────────────────────────────────────
  const [report, setReport] = useState<QualityReport | null>(null);
  const [projThreshold, setProjThreshold] = useState(80);

  // ── Step 3: redrive ─────────────────────────────────────────────────
  const [defaultAction, setDefaultAction] = useState<RecommendedAction | "">("");
  const [bucketRoutes, setBucketRoutes] = useState<Record<string, BucketRoute>>(emptyBucketRoutes());
  const [run, setRun] = useState<RedriveRun | null>(null);
  const [actor, setActor] = useState("reviewer@example.com");

  // ── Ancillary tools (unchanged, independent of the wizard) ──────────
  const [evalUnitId, setEvalUnitId] = useState("");
  const [evalProvider, setEvalProvider] = useState("");
  const [evalModel, setEvalModel] = useState("");
  const [evalRefMode, setEvalRefMode] = useState("auto");
  const [evalResult, setEvalResult] = useState<EvaluateResult | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [meteorHyp, setMeteorHyp] = useState("");
  const [meteorRef, setMeteorRef] = useState("");
  const [meteorScore, setMeteorScore] = useState<number | null | undefined>(undefined);
  const [meteorBusy, setMeteorBusy] = useState(false);
  const [crowdin, setCrowdin] = useState<{ configured: boolean; project_id: string | null; detail: string | null } | null>(null);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookMsg, setWebhookMsg] = useState<string | null>(null);

  useEffect(() => { api.listStyleGuides().then(setGuides).catch(() => {}); }, []);
  useEffect(() => { api.listQualityReports(10).then(setRecent).catch(() => {}); }, []);
  useEffect(() => { api.tmsStatus().then(setCrowdin).catch(() => {}); }, []);

  async function setupCrowdinWebhook() {
    if (!webhookUrl.trim()) return;
    setWebhookMsg(null);
    try {
      const r = await api.tmsSetupWebhook(webhookUrl.trim());
      setWebhookMsg(`${r.created ? "Registered" : "Already registered"} for ${r.events.join(", ")}.`);
    } catch (e) {
      setWebhookMsg(e instanceof Error ? e.message : String(e));
    }
  }

  // Any change to the routing plan invalidates a prior approval.
  useEffect(() => {
    setPlanApproved(false);
  }, [defaultAction, bucketRoutes, redriveProvider, redriveModel, secondReview]);

  const isMprometheus = scoringProvider === "mprometheus";
  const pipelineEngineLabel = redriveProvider
    ? `${providerLabel(TRANSLATE_PROVIDERS, redriveProvider)}${redriveModel ? ` / ${redriveModel}` : ""}`
    : "app default engine";

  async function buildReport() {
    setBusy(true);
    setError(null);
    try {
      const scope = targetLanguage ? { target_language: targetLanguage } : {};
      const r = await api.createQualityReport({
        scope, threshold,
        style_threshold: styleEnabled ? styleThreshold : undefined,
        style_guide_id: styleEnabled ? (styleGuideId || undefined) : undefined,
        scoring_provider: scoringProvider || undefined,
        scoring_model: scoringModel || undefined,
        reference_mode: isMprometheus ? referenceMode : undefined,
        triggered_by: triggeredBy || undefined,
      });
      setReport(r);
      setProjThreshold(r.quality_threshold);
      setRun(null);
      // The "pause on the report" gate decides whether we stop here for a
      // human to eyeball the buckets, or drop straight into routing.
      setStep(gatePauseOnReport ? "report" : "redrive");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadRecent(id: string) {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.getQualityReport(id);
      setReport(r);
      setProjThreshold(r.quality_threshold);
      setRun(null);
      setStep("report");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function setItemRoute(item: QualityReportItem, action: RecommendedAction | "") {
    if (!report) return;
    const updated = await api.setReportItemRoute(report.id, item.id, action || null);
    setReport({ ...report, items: report.items.map((it) => (it.id === updated.id ? updated : it)) });
  }

  async function attachSpans(kind: "xcomet" | "cometkiwi") {
    if (!report) return;
    setBusy(true);
    setError(null);
    try {
      const updated = kind === "xcomet"
        ? await api.attachReportXcomet(report.id)
        : await api.attachReportCometkiwi(report.id);
      setReport(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // Resolve what actually happens to a bucket, mirroring the backend's
  // precedence: an explicit per-bucket action wins, else the default
  // action, else the report's own per-item recommendation. The engine is
  // the bucket's own override, else the pipeline retranslate engine.
  function bucketPlan(b: string): { action: string; engine: string } {
    const r = bucketRoutes[b];
    const action = r.action || defaultAction || "";
    const actionLabel = action
      ? (ACTION_OPTIONS.find((o) => o.value === action)?.label ?? action)
      : "report's recommendation";
    let engine = "—";
    if (action === "mt" || action === "human" || action === "") {
      engine = r.override && r.provider ? `${providerLabel(TRANSLATE_PROVIDERS, r.provider)}${r.model ? ` / ${r.model}` : ""}` : pipelineEngineLabel;
    }
    if (action === "none") engine = "—";
    return { action: actionLabel, engine };
  }

  function buildRouting(): RedriveRouting {
    const routing: RedriveRouting = {};
    if (defaultAction) {
      routing.default = {
        action: defaultAction,
        provider: redriveProvider || undefined,
        model: redriveModel || undefined,
      };
    }
    const byBucket: Record<string, RoutingTarget> = {};
    for (const b of ACTIONABLE_BUCKETS) {
      const r = bucketRoutes[b];
      if (!r.action) continue; // no explicit rule → falls through to default / recommendation
      byBucket[b] = {
        action: r.action,
        provider: (r.override && r.provider) || redriveProvider || undefined,
        model: (r.override && r.model) || (!r.override ? redriveModel : "") || undefined,
        review_venue: r.action === "human" && r.sendToCrowdin ? "crowdin" : undefined,
      };
    }
    if (Object.keys(byBucket).length) routing.by_bucket = byBucket;
    return routing;
  }

  async function runRedrive() {
    if (!report) return;
    if (gateApprovePlan && !planApproved) {
      setError("Approve the routing plan below before running the redrive.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const routing = buildRouting();
      const result = await api.createRedriveRun({
        threshold: report.quality_threshold, scope: {},
        from_report_id: report.id,
        routing: Object.keys(routing).length ? routing : undefined,
        second_review: secondReview,
        triggered_by: triggeredBy || undefined,
      });
      setRun(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doEvaluate() {
    if (!evalUnitId.trim()) return;
    setEvaluating(true);
    try {
      setEvalResult(await api.evaluateUnit(
        evalUnitId.trim(), evalProvider || undefined, evalModel || undefined,
        evalProvider === "mprometheus" ? evalRefMode : undefined,
      ));
    } finally {
      setEvaluating(false);
    }
  }

  async function doMeteorCompare() {
    if (!meteorHyp.trim() || !meteorRef.trim()) return;
    setMeteorBusy(true);
    try {
      const { score } = await api.meteorCompare(meteorHyp.trim(), meteorRef.trim());
      setMeteorScore(score);
    } finally {
      setMeteorBusy(false);
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

  const projectedCounts = useMemo(() => {
    if (!report) return null;
    const counts: Record<string, number> = { pass: 0, below_quality: 0, hard_fail: 0, below_style: 0, needs_review: 0 };
    for (const it of report.items) counts[projectBucket(it, projThreshold, report.style_threshold)]++;
    return counts;
  }, [report, projThreshold]);

  const issues = useMemo(
    () => (report ? [...report.items].filter((it) => it.bucket !== "pass").sort(
      (a, b) => (a.before_score ?? -1) - (b.before_score ?? -1),
    ) : []),
    [report],
  );

  return (
    <div style={{ padding: 24, maxWidth: 860 }}>
      <PageIntro
        title="Redrive Console"
        requires="pick a scope + evaluator below and build a quality report — nothing is retranslated until you route the report's issues and run the redrive in step 3."
      >
        Translate → <strong>evaluate</strong> → <strong>report</strong> → <strong>redrive</strong>. The report is a
        halting checkpoint: it spends no translation budget, it's exportable, and you decide per bucket (or per unit)
        whether each issue goes to a human reviewer or straight to an MT engine.
      </PageIntro>

      {/* ── Pipeline: models per step + approval gates ─────────────────── */}
      <details open style={{ margin: "4px 0 16px", border: "1px solid #e5e7eb", borderRadius: 8 }}>
        <summary style={{ cursor: "pointer", padding: "10px 14px", fontSize: 13, fontWeight: 600, userSelect: "none" }}>
          Pipeline — models &amp; approval gates
        </summary>
        <div style={{ padding: "4px 14px 14px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            Pick the model for each step once. The retranslate engine below is the default for every MT / human-draft
            route in step 3; a bucket can still override it. (The initial <em>translate</em> engine is chosen on the
            Content Creation / Import screens.)
          </div>

          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <div>
              <ModelPicker
                providers={EVALUATE_PROVIDERS} provider={scoringProvider} model={scoringModel}
                onProviderChange={setScoringProvider} onModelChange={setScoringModel} label="Evaluate with"
              />
              {isMprometheus && (
                <div style={{ marginTop: 6, fontSize: 12, color: "#92400e", maxWidth: 300 }}>
                  Research/non-commercial (Qwen Research License) — its scores are stamped non-commercial on the report.
                  <label style={{ display: "block", marginTop: 6, color: "#374151" }}>
                    Reference mode
                    <select value={referenceMode} onChange={(e) => setReferenceMode(e.target.value)}
                            style={{ display: "block", padding: 4, marginTop: 4, minWidth: 260 }}>
                      {MPROMETHEUS_REFERENCE_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </select>
                  </label>
                </div>
              )}
            </div>
            <div>
              <ModelPicker
                providers={TRANSLATE_PROVIDERS} provider={redriveProvider} model={redriveModel}
                onProviderChange={setRedriveProvider} onModelChange={setRedriveModel} label="Retranslate with"
              />
              <div style={{ marginTop: 6, fontSize: 12, color: "#6b7280", maxWidth: 300 }}>
                Default for every routed MT / human-draft in step 3.
              </div>
            </div>
          </div>

          <fieldset style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "8px 12px 12px", margin: 0 }}>
            <legend style={{ fontSize: 12, fontWeight: 600, color: "#374151", padding: "0 6px" }}>Approval gates</legend>
            <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
              <input type="checkbox" checked={gatePauseOnReport} onChange={(e) => setGatePauseOnReport(e.target.checked)} />
              Pause on the quality report before routing anything <span style={{ color: "#9ca3af" }}>(recommended)</span>
            </label>
            <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6, marginTop: 8 }}>
              <input type="checkbox" checked={gateApprovePlan} onChange={(e) => setGateApprovePlan(e.target.checked)} />
              Require me to approve the routing plan before the redrive runs
            </label>
            <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6, marginTop: 8 }}>
              <input type="checkbox" checked={secondReview} onChange={(e) => setSecondReview(e.target.checked)} />
              Second review — hold every MT candidate for human sign-off, even when it clears the threshold
            </label>
          </fieldset>
        </div>
      </details>

      {/* Step nav */}
      <div style={{ display: "flex", gap: 6, margin: "8px 0 20px" }}>
        {(["evaluate", "report", "redrive"] as Step[]).map((s) => {
          const enabled = s === "evaluate" || (report !== null);
          return (
            <button
              key={s}
              disabled={!enabled}
              onClick={() => enabled && setStep(s)}
              style={{
                padding: "5px 12px", fontSize: 13, cursor: enabled ? "pointer" : "not-allowed",
                borderRadius: 6, border: "1px solid #d1d5db",
                background: step === s ? "#111827" : "#fff", color: step === s ? "#fff" : "#374151",
                opacity: enabled ? 1 : 0.5,
              }}
            >
              {STEP_TITLE[s]}
            </button>
          );
        })}
      </div>

      {error && (
        <div style={{ marginBottom: 16, padding: "8px 12px", background: "#fef2f2", color: "#b91c1c", borderRadius: 6, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* ── Step 1 ──────────────────────────────────────────────────── */}
      {step === "evaluate" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <LocaleSelect value={targetLanguage} onChange={setTargetLanguage} label="Target language" blankLabel="All languages" width={200} />
          <label style={{ fontSize: 13 }}>
            Quality threshold: <strong>{threshold}</strong>
            <input type="range" min={0} max={100} value={threshold}
                   onChange={(e) => setThreshold(Number(e.target.value))} style={{ display: "block", width: 300 }} />
          </label>

          <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={styleEnabled} onChange={(e) => setStyleEnabled(e.target.checked)} />
            Also flag units below a style/voice score
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

          <div style={{ fontSize: 12.5, color: "#6b7280" }}>
            Evaluator: <strong>{scoringProvider || "app default"}{scoringModel ? ` / ${scoringModel}` : ""}</strong>
            {" "}— change it in the <em>Pipeline</em> panel above.
          </div>

          <label style={{ fontSize: 13 }}>
            Triggered by
            <input value={triggeredBy} onChange={(e) => setTriggeredBy(e.target.value)}
                   style={{ display: "block", width: 240, marginTop: 4, padding: 4 }} />
          </label>

          <div>
            <button disabled={busy} onClick={buildReport} style={{ padding: "7px 16px", cursor: "pointer", fontWeight: 600 }}>
              {busy ? "Scoring…" : "Build quality report"}
            </button>
          </div>

          {recent.length > 0 && (
            <label style={{ fontSize: 13, marginTop: 8 }}>
              …or reopen a recent report
              <select defaultValue="" onChange={(e) => loadRecent(e.target.value)}
                      style={{ display: "block", padding: 4, marginTop: 4, minWidth: 360 }}>
                <option value="">Select a report…</option>
                {recent.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id.slice(0, 8)} · {new Date(r.created_at).toLocaleString()} · {r.scoring_provider}
                    {" · "}{r.totals.below_threshold ?? 0} below
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {/* ── Step 2 ──────────────────────────────────────────────────── */}
      {step === "report" && report && (
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ fontSize: 13, color: "#6b7280" }}>
            Report <span style={{ fontFamily: "monospace" }}>{report.id.slice(0, 8)}</span> ·
            evaluator <strong>{report.scoring_provider}{report.scoring_model ? ` / ${report.scoring_model}` : ""}</strong> ·
            threshold {report.quality_threshold}
            {report.style_threshold !== null && <> · style {report.style_threshold}</>}
          </div>

          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <div style={{ minWidth: 320 }}>
              <BarChart
                data={(["pass", ...ACTIONABLE_BUCKETS] as QualityBucket[]).map((b) => ({
                  label: BUCKET_LABEL[b],
                  value: report.summary[b] ?? 0,
                  color: BUCKET_COLOR[b],
                }))}
              />
            </div>
            <div style={{ fontSize: 13, color: "#374151", display: "flex", flexDirection: "column", gap: 3 }}>
              <div><strong>{report.totals.units ?? report.items.length}</strong> units evaluated</div>
              <div><strong>{report.totals.below_threshold ?? 0}</strong> below quality (incl. critical)</div>
              <div><strong>{report.totals.needs_review ?? 0}</strong> unscoreable</div>
              <div><strong>{(report.totals.est_source_chars ?? 0).toLocaleString()}</strong> source chars to redrive</div>
              <div style={{ marginTop: 4 }}>
                commercial: <strong style={{ color: "#6b7280" }}>{report.totals.commercial_safe ?? 0} safe</strong>
                {" / "}
                <strong style={{ color: "#e5484d" }}>{report.totals.non_commercial ?? 0} non-comm</strong>
                {(report.totals.commercial_unknown ?? 0) > 0 && <> / <strong style={{ color: "#92400e" }}>{report.totals.commercial_unknown} unknown</strong></>}
              </div>
            </div>
          </div>

          {/* threshold projection */}
          <div style={{ padding: 12, background: "#f9fafb", borderRadius: 6, fontSize: 13 }}>
            <label>
              Try a different threshold: <strong>{projThreshold}</strong>
              <input type="range" min={0} max={100} value={projThreshold}
                     onChange={(e) => setProjThreshold(Number(e.target.value))} style={{ display: "block", width: 320 }} />
            </label>
            {projectedCounts && (
              <div style={{ marginTop: 6, color: "#6b7280" }}>
                at {projThreshold}: {projectedCounts.pass} pass · {projectedCounts.below_quality} below quality ·
                {" "}{projectedCounts.hard_fail} critical · {projectedCounts.below_style} below style ·
                {" "}{projectedCounts.needs_review} needs review
                {projThreshold !== report.quality_threshold && (
                  <button
                    disabled={busy}
                    onClick={() => { setThreshold(projThreshold); buildReport(); }}
                    style={{ marginLeft: 10, fontSize: 12, cursor: "pointer" }}
                  >
                    Rebuild report at {projThreshold}
                  </button>
                )}
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <a href={qualityReportJsonUrl(report.id)} style={{ fontSize: 13 }}>Download JSON</a>
            <a href={qualityReportPdfUrl(report.id)} style={{ fontSize: 13 }}>Download PDF</a>
            <span style={{ color: "#d1d5db" }}>|</span>
            <button disabled={busy} onClick={() => attachSpans("xcomet")} style={{ fontSize: 12, cursor: "pointer" }}>
              Attach XCOMET spans
            </button>
            <button disabled={busy} onClick={() => attachSpans("cometkiwi")} style={{ fontSize: 12, cursor: "pointer" }}>
              Attach CometKiwi tags
            </button>
            <span style={{ fontSize: 11, color: "#9ca3af" }}>(non-commercial · needs unbabel-comet)</span>
          </div>

          <div>
            <h3 style={{ fontSize: 15, marginBottom: 8 }}>Quality issues ({issues.length})</h3>
            {issues.length === 0 ? (
              <div style={{ fontSize: 13, color: "#9ca3af" }}>Everything in scope passed — nothing to redrive.</div>
            ) : (
              <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                    <th style={{ padding: "4px 6px" }}>Score</th>
                    <th style={{ padding: "4px 6px" }}>Bucket</th>
                    <th style={{ padding: "4px 6px" }}>Reasons</th>
                    <th style={{ padding: "4px 6px" }}>Spans</th>
                    <th style={{ padding: "4px 6px" }}>Comm.</th>
                    <th style={{ padding: "4px 6px" }}>Route</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.map((it) => {
                    const tag = commercialTag(it.commercial_safe);
                    return (
                      <tr key={it.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                        <td style={{ padding: "4px 6px" }}>
                          <QualityBadge score={it.before_score} hardFail={it.hard_fail} />
                        </td>
                        <td style={{ padding: "4px 6px", color: BUCKET_COLOR[it.bucket], fontWeight: 600 }}>
                          {BUCKET_LABEL[it.bucket]}
                        </td>
                        <td style={{ padding: "4px 6px", color: "#6b7280", maxWidth: 280 }}>
                          {it.reasons.join("; ") || (it.hard_fail ? "critical error" : "—")}
                        </td>
                        <td style={{ padding: "4px 6px", color: "#6b7280" }}
                            title={it.error_spans.map((s) => `${s.source ?? "?"}: ${s.severity} "${s.text ?? ""}"`).join("\n")}>
                          {it.error_spans.length > 0
                            ? `${it.error_spans.length} (${[...new Set(it.error_spans.map((s) => s.source))].join(", ")})`
                            : "—"}
                        </td>
                        <td style={{ padding: "4px 6px", color: tag.color, fontWeight: tag.text === "NON-COMM" ? 700 : 400 }}>
                          {tag.text}
                        </td>
                        <td style={{ padding: "4px 6px" }}>
                          <select
                            value={it.route_override ?? ""}
                            onChange={(e) => setItemRoute(it, e.target.value as RecommendedAction | "")}
                            style={{ fontSize: 11, padding: 2 }}
                          >
                            <option value="">rec: {it.recommended_action}</option>
                            <option value="none">none</option>
                            <option value="human">human</option>
                            <option value="mt">mt</option>
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div>
            <button onClick={() => setStep("redrive")} disabled={issues.length === 0}
                    style={{ padding: "7px 16px", cursor: issues.length === 0 ? "not-allowed" : "pointer", fontWeight: 600 }}>
              Continue to redrive →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3 ──────────────────────────────────────────────────── */}
      {step === "redrive" && report && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ fontSize: 13, color: "#6b7280" }}>
            Routing the {issues.length} issue(s) from report{" "}
            <span style={{ fontFamily: "monospace" }}>{report.id.slice(0, 8)}</span>. A per-unit override set in step 2
            wins over the bucket rule below. Buckets with no rule use the retranslate engine from the{" "}
            <em>Pipeline</em> panel: <strong>{pipelineEngineLabel}</strong>.
          </div>

          <label style={{ fontSize: 13 }}>
            Default action (buckets without a rule below)
            <select value={defaultAction} onChange={(e) => setDefaultAction(e.target.value as RecommendedAction | "")}
                    style={{ display: "block", padding: 4, marginTop: 4, minWidth: 300 }}>
              {ACTION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {ACTIONABLE_BUCKETS.map((b) => {
              const r = bucketRoutes[b];
              const count = report.summary[b] ?? 0;
              const effectiveAction = r.action || defaultAction;
              return (
                <div key={b} style={{ padding: 10, background: "#f9fafb", borderRadius: 6, opacity: count === 0 ? 0.5 : 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: BUCKET_COLOR[b], marginBottom: 6 }}>
                    {BUCKET_LABEL[b]} <span style={{ color: "#9ca3af", fontWeight: 400 }}>· {count} unit(s)</span>
                  </div>
                  <select
                    value={r.action}
                    onChange={(e) => setBucketRoutes({ ...bucketRoutes, [b]: { ...r, action: e.target.value as RecommendedAction | "" } })}
                    style={{ fontSize: 13, padding: 4, minWidth: 300 }}
                  >
                    {ACTION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  {(effectiveAction === "mt" || effectiveAction === "human") && (
                    <div style={{ marginTop: 8 }}>
                      <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
                        <input
                          type="checkbox" checked={r.override}
                          onChange={(e) => setBucketRoutes({ ...bucketRoutes, [b]: { ...r, override: e.target.checked } })}
                        />
                        Override the pipeline engine for this bucket
                      </label>
                      {r.override ? (
                        <div style={{ marginTop: 6 }}>
                          <ModelPicker
                            providers={TRANSLATE_PROVIDERS} provider={r.provider} model={r.model}
                            onProviderChange={(p) => setBucketRoutes({ ...bucketRoutes, [b]: { ...bucketRoutes[b], provider: p } })}
                            onModelChange={(m) => setBucketRoutes({ ...bucketRoutes, [b]: { ...bucketRoutes[b], model: m } })}
                            label={effectiveAction === "mt" ? "Retranslate with" : "Draft for the reviewer with"}
                          />
                        </div>
                      ) : (
                        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
                          Uses the pipeline engine: <strong>{pipelineEngineLabel}</strong>
                        </div>
                      )}
                      {effectiveAction === "human" && (
                        <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
                          <input
                            type="checkbox" checked={r.sendToCrowdin}
                            onChange={(e) => setBucketRoutes({ ...bucketRoutes, [b]: { ...r, sendToCrowdin: e.target.checked } })}
                          />
                          Send to Crowdin for review <span style={{ color: "#9ca3af" }}>
                            (instead of the in-app approval queue — the draft goes as a suggestion)
                          </span>
                        </label>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Routing plan — what will actually happen, engine included */}
          <div style={{ padding: 12, background: "#f8fafc", border: "1px solid #e5e7eb", borderRadius: 6 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Routing plan</div>
            <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                  <th style={{ padding: "3px 6px" }}>Bucket</th>
                  <th style={{ padding: "3px 6px" }}>Units</th>
                  <th style={{ padding: "3px 6px" }}>Action</th>
                  <th style={{ padding: "3px 6px" }}>Engine</th>
                </tr>
              </thead>
              <tbody>
                {ACTIONABLE_BUCKETS.filter((b) => (report.summary[b] ?? 0) > 0).map((b) => {
                  const plan = bucketPlan(b);
                  return (
                    <tr key={b} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "3px 6px", color: BUCKET_COLOR[b], fontWeight: 600 }}>{BUCKET_LABEL[b]}</td>
                      <td style={{ padding: "3px 6px" }}>{report.summary[b] ?? 0}</td>
                      <td style={{ padding: "3px 6px" }}>{plan.action}</td>
                      <td style={{ padding: "3px 6px", color: "#6b7280" }}>{plan.engine}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 6 }}>
              {secondReview
                ? "Second review is on — every MT candidate is held for sign-off regardless of its score."
                : "MT candidates that clear the threshold on a second-pass score go live immediately; the rest are held as pending approvals."}
            </div>
          </div>

          {gateApprovePlan && (
            <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6, padding: "8px 12px", background: "#fffbeb", borderRadius: 6 }}>
              <input type="checkbox" checked={planApproved} onChange={(e) => setPlanApproved(e.target.checked)} />
              I have reviewed the routing plan above and approve running the redrive
            </label>
          )}

          <label style={{ fontSize: 13 }}>
            Approving/rejecting as
            <input value={actor} onChange={(e) => setActor(e.target.value)}
                   style={{ display: "block", width: 240, marginTop: 4, padding: 4 }} />
          </label>

          <div>
            <button
              disabled={busy || (gateApprovePlan && !planApproved)}
              onClick={runRedrive}
              style={{
                padding: "7px 16px", fontWeight: 600,
                cursor: busy || (gateApprovePlan && !planApproved) ? "not-allowed" : "pointer",
              }}
            >
              {busy ? "Running…" : "Run redrive from report"}
            </button>
          </div>

          {run && (
            <div>
              <h3 style={{ fontSize: 15 }}>Run {run.id.slice(0, 8)} — {run.status}</h3>
              <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 8 }}>
                {Object.entries(run.summary).map(([k, v]) => `${k}: ${v}`).join(" · ")}
              </div>
              <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                    <th>Unit</th><th>Before</th><th>After</th><th>Outcome</th><th>Detail</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {run.items.map((item) => (
                    <tr key={item.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ fontFamily: "monospace", fontSize: 11 }}>{item.unit_id.slice(0, 8)}</td>
                      <td><QualityBadge score={item.before_score} /></td>
                      <td><QualityBadge score={item.after_score} /></td>
                      <td>{item.outcome}</td>
                      <td style={{ fontSize: 11, color: "#6b7280", maxWidth: 280 }}>{item.detail}</td>
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
      )}

      {/* ── Ancillary tools ────────────────────────────────────────── */}
      <hr style={{ margin: "28px 0 18px", border: "none", borderTop: "1px solid #e5e7eb" }} />
      <h3 style={{ fontSize: 14, color: "#6b7280" }}>Tools</h3>

      <div style={{ marginBottom: 20, padding: 12, background: "#f9fafb", borderRadius: 6 }}>
        <h4 style={{ marginTop: 0, fontSize: 14 }}>Crowdin (TMS)</h4>
        <p style={{ color: "#6b7280", fontSize: 13, marginTop: 0 }}>
          {crowdin === null
            ? "Checking…"
            : crowdin.configured
              ? <>Connected to project <strong>{crowdin.project_id}</strong>. A <em>human</em> bucket above can be
                sent to Crowdin for review; approved translations return via the webhook below.</>
              : <>Not configured — set <code>CROWDIN_PROJECT_ID</code> / <code>CROWDIN_API_TOKEN</code> in <code>.env</code>. {crowdin.detail}</>}
        </p>
        {crowdin?.configured && (
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://<public-host>/api/v1/integrations/tms/webhook?secret=<CROWDIN_WEBHOOK_SECRET>"
              style={{ flex: 1, minWidth: 360, fontSize: 12, padding: 5 }}
            />
            <button onClick={setupCrowdinWebhook} disabled={!webhookUrl.trim()} style={{ fontSize: 12, cursor: "pointer" }}>
              Set up webhook
            </button>
            {webhookMsg && <span style={{ fontSize: 12, color: "#6b7280" }}>{webhookMsg}</span>}
          </div>
        )}
      </div>

      <div id="evaluate-single-unit" style={{ marginBottom: 20, padding: 12, background: "#f9fafb", borderRadius: 6 }}>
        <h4 style={{ marginTop: 0, fontSize: 14 }}>Evaluate a single unit</h4>
        <p style={{ color: "#6b7280", fontSize: 13, marginTop: 0 }}>
          Score one unit on demand with a chosen model — independent of the report flow. Requires a unit id.
        </p>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13 }}>
            Unit id
            <input value={evalUnitId} onChange={(e) => setEvalUnitId(e.target.value)}
                   placeholder="unit id" style={{ display: "block", width: 260, marginTop: 4, padding: 4 }} />
          </label>
          <ModelPicker
            providers={EVALUATE_PROVIDERS} provider={evalProvider} model={evalModel}
            onProviderChange={setEvalProvider} onModelChange={setEvalModel} label="Evaluate with"
          />
          {evalProvider === "mprometheus" && (
            <label style={{ fontSize: 13 }}>
              Reference mode
              <select value={evalRefMode} onChange={(e) => setEvalRefMode(e.target.value)}
                      style={{ display: "block", padding: 4, marginTop: 4, minWidth: 220 }}>
                {MPROMETHEUS_REFERENCE_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </label>
          )}
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
            {evalResult.reasons.length > 0 && <div style={{ color: "#6b7280" }}>{evalResult.reasons.join(", ")}</div>}
          </div>
        )}
      </div>

      <div style={{ marginBottom: 20, padding: 12, background: "#f9fafb", borderRadius: 6 }}>
        <h4 style={{ marginTop: 0, fontSize: 14 }}>Compare METEOR</h4>
        <p style={{ color: "#6b7280", fontSize: 13, marginTop: 0 }}>
          Ad-hoc lexical comparison between any two strings — the same computation that runs automatically after every redrive.
        </p>
        <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
          <textarea value={meteorHyp} onChange={(e) => setMeteorHyp(e.target.value)} rows={2}
                    placeholder="Candidate text" style={{ flex: 1, fontSize: 13, padding: 6 }} />
          <textarea value={meteorRef} onChange={(e) => setMeteorRef(e.target.value)} rows={2}
                    placeholder="Reference text" style={{ flex: 1, fontSize: 13, padding: 6 }} />
        </div>
        <button disabled={meteorBusy || !meteorHyp.trim() || !meteorRef.trim()} onClick={doMeteorCompare}
                style={{ padding: "6px 14px", cursor: "pointer" }}>
          {meteorBusy ? "Comparing…" : "Compare"}
        </button>
        {meteorScore !== undefined && (
          <span style={{ marginLeft: 12, fontSize: 13 }}>
            {meteorScore === null
              ? <span style={{ color: "#92400e" }}>Unavailable — nltk/wordnet not installed on the server.</span>
              : <>METEOR: <strong>{meteorScore.toFixed(1)}</strong></>}
          </span>
        )}
      </div>
    </div>
  );
}
