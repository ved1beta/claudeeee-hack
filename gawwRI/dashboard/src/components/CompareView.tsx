import { useState, useEffect, useCallback } from "react";
import type { AnalysisData } from "../types";

const API = "http://localhost:8000";

/** A named dataset that can be selected in the picker */
export interface DatasetOption {
  id: string;
  label: string;
  group: "demo" | "history";
  data?: AnalysisData; // pre-loaded for demo datasets
  sessionId?: string;  // for history datasets — fetched on demand
}

interface CompareViewProps {
  unprotected: AnalysisData;
  protected_: AnalysisData;
  onClose: () => void;
  /** When true, uses generic "Session A / Session B" labels instead of "Without/With AgentLens" */
  isCustomCompare?: boolean;
  /** Pre-loaded demo datasets available for selection */
  demoDatasets?: DatasetOption[];
  /** Whether the backend server is online (for fetching history) */
  serverOnline?: boolean;
}

function getHealthColor(score: number): string {
  if (score >= 80) return "#22c55e";
  if (score >= 55) return "#f59e0b";
  if (score >= 30) return "#f97316";
  return "#ef4444";
}

function getHealthLabel(score: number): string {
  if (score >= 80) return "HEALTHY";
  if (score >= 55) return "DEGRADED";
  if (score >= 30) return "FAILING";
  return "CRITICAL";
}

function MiniGauge({ score, size = 100 }: { score: number; size?: number }) {
  const color = getHealthColor(score);
  const svgW = size;
  const svgH = size * 0.6;
  const r = size * 0.4;
  const cx = svgW / 2;
  const cy = svgH - 5;
  const circumference = Math.PI * r;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center">
      <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke="#1a1a1a"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={`${offset}`}
          style={{ transition: "stroke-dashoffset 1s ease" }}
        />
        <text
          x={cx}
          y={cy - 5}
          textAnchor="middle"
          fill={color}
          fontSize={size * 0.28}
          fontWeight="bold"
          fontFamily="monospace"
        >
          {score}
        </text>
      </svg>
      <span className="text-xs tracking-widest font-bold mt-1" style={{ color }}>
        {getHealthLabel(score)}
      </span>
    </div>
  );
}

function getStepColor(
  step: AnalysisData["steps"][0],
  anomalies: AnalysisData["anomalies"]
): string {
  if (step.guardrail_injected) return "#3b82f6";
  // Check anomalies
  for (const a of anomalies.loops) {
    if (a.start_step && a.end_step && step.step_id >= a.start_step && step.step_id <= a.end_step) return "#ef4444";
  }
  for (const a of anomalies.error_spirals) {
    if (a.start_step && a.current_step && step.step_id >= a.start_step && step.step_id <= a.current_step) return "#ef4444";
  }
  for (const a of anomalies.context_decay) {
    if (a.step_id === step.step_id) return "#f59e0b";
  }
  const pct = step.trajectory_metrics.context_utilization_pct;
  if (pct > 70) return "#ef4444";
  if (pct > 40) return "#f59e0b";
  return "#22c55e";
}

function MiniTimeline({ data, label }: { data: AnalysisData; label: string }) {
  const guardrailCount = data.guardrails_triggered?.length || data.steps.filter((s) => s.guardrail_injected).length;
  const anomalyCount =
    data.anomalies.loops.length +
    data.anomalies.error_spirals.length +
    data.anomalies.context_decay.length +
    data.anomalies.repetition.length;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-xs font-medium tracking-widest uppercase text-white/40">{label}</h3>
        {anomalyCount > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 font-bold">
            {anomalyCount} anomalies
          </span>
        )}
        {guardrailCount > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 font-bold">
            {guardrailCount} guards fired
          </span>
        )}
      </div>
      <div className="overflow-x-auto pb-2">
        <div className="flex items-center gap-0.5 min-w-max">
          {data.steps.map((step, i) => {
            const color = getStepColor(step, data.anomalies);
            return (
              <div key={step.step_id} className="flex items-center">
                <div className="relative flex flex-col items-center group">
                  {step.guardrail_injected && (
                    <span className="text-[6px] px-0.5 py-0 rounded bg-blue-500/20 text-blue-400 font-bold mb-0.5">
                      GUARD
                    </span>
                  )}
                  <div
                    className="w-6 h-6 rounded-full border-2 flex items-center justify-center text-[8px] font-mono font-bold"
                    style={{
                      borderColor: color,
                      backgroundColor: `${color}20`,
                      color: color,
                    }}
                  >
                    {step.step_id}
                  </div>
                  {/* Tooltip on hover */}
                  <div className="absolute bottom-full mb-1 hidden group-hover:block z-10 bg-black border border-white/20 rounded px-2 py-1 text-[9px] text-white/70 whitespace-nowrap">
                    {step.response.tools_called.map((t) => t.name).join(", ") || step.response.text_summary?.slice(0, 40) || "—"}
                  </div>
                </div>
                {i < data.steps.length - 1 && <div className="w-2 h-px bg-white/10" />}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function StatRow({ label, left, right, better }: { label: string; left: string | number; right: string | number; better?: "left" | "right" }) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 py-1.5 border-b border-white/5 last:border-0">
      <div className={`text-right font-mono text-sm ${better === "right" ? "text-white/50" : "text-white/80"}`}>
        {left}
      </div>
      <div className="text-[10px] text-white/30 uppercase tracking-wider w-24 text-center">{label}</div>
      <div className={`font-mono text-sm ${better === "left" ? "text-white/50" : "text-white/80"}`}>
        {right}
      </div>
    </div>
  );
}

export default function CompareView({ unprotected, protected_, onClose, isCustomCompare, demoDatasets, serverOnline }: CompareViewProps) {
  // --- Dataset picker state ---
  const [allOptions, setAllOptions] = useState<DatasetOption[]>(demoDatasets || []);
  const [leftId, setLeftId] = useState<string>("");
  const [rightId, setRightId] = useState<string>("");
  const [leftData, setLeftData] = useState<AnalysisData>(unprotected);
  const [rightData, setRightData] = useState<AnalysisData>(protected_);
  const [loadingLeft, setLoadingLeft] = useState(false);
  const [loadingRight, setLoadingRight] = useState(false);
  const [showPicker, setShowPicker] = useState(false);

  // Fetch history sessions on mount
  useEffect(() => {
    if (!serverOnline) return;
    fetch(`${API}/history`)
      .then((r) => r.json())
      .then((d) => {
        const historyOptions: DatasetOption[] = (d.sessions || []).map((s: { session_id: string; display_name?: string; total_steps: number }) => ({
          id: `history:${s.session_id}`,
          label: `${s.display_name || s.session_id.slice(0, 24)} (${s.total_steps} steps)`,
          group: "history" as const,
          sessionId: s.session_id,
        }));
        setAllOptions((prev) => {
          // Merge: keep demos, replace history
          const demos = prev.filter((o) => o.group === "demo");
          return [...demos, ...historyOptions];
        });
      })
      .catch(() => { /* server offline */ });
  }, [serverOnline]);

  const loadDataset = useCallback(async (option: DatasetOption): Promise<AnalysisData | null> => {
    if (option.data) return option.data;
    if (option.sessionId) {
      try {
        const r = await fetch(`${API}/history/${option.sessionId}`);
        if (r.ok) return await r.json() as AnalysisData;
      } catch { /* ignore */ }
    }
    return null;
  }, []);

  const handleLeftChange = useCallback(async (id: string) => {
    setLeftId(id);
    if (!id) { setLeftData(unprotected); return; }
    const opt = allOptions.find((o) => o.id === id);
    if (!opt) return;
    setLoadingLeft(true);
    const d = await loadDataset(opt);
    if (d) setLeftData(d);
    setLoadingLeft(false);
  }, [allOptions, loadDataset, unprotected]);

  const handleRightChange = useCallback(async (id: string) => {
    setRightId(id);
    if (!id) { setRightData(protected_); return; }
    const opt = allOptions.find((o) => o.id === id);
    if (!opt) return;
    setLoadingRight(true);
    const d = await loadDataset(opt);
    if (d) setRightData(d);
    setLoadingRight(false);
  }, [allOptions, loadDataset, protected_]);

  const u = leftData;
  const p = rightData;

  const uFailed = u.health_score < 30;
  const pSucceeded = p.health_score >= 60;

  const uAnomalyCount = u.anomalies.loops.length + u.anomalies.error_spirals.length + u.anomalies.context_decay.length;
  const pAnomalyCount = p.anomalies.loops.length + p.anomalies.error_spirals.length + p.anomalies.context_decay.length;
  const uGuardrailCount = u.guardrails_triggered?.length || u.steps.filter((s) => s.guardrail_injected).length;
  const pGuardrailCount = p.guardrails_triggered?.length || p.steps.filter((s) => s.guardrail_injected).length;

  // For custom compare, determine which is "better"
  const isCustom = isCustomCompare || !!leftId || !!rightId;
  const leftBetter = u.health_score > p.health_score;
  const healthDiff = Math.abs(p.health_score - u.health_score);
  const stepsDiff = Math.abs(u.steps.length - p.steps.length);

  // Labels
  const leftLabel = isCustom ? (u.session_id?.slice(0, 20) || "Session A") : "Without AgentLens";
  const rightLabel = isCustom ? (p.session_id?.slice(0, 20) || "Session B") : "With AgentLens";
  const leftColor = isCustom ? (leftBetter ? "green" : "red") : "red";
  const rightColor = isCustom ? (leftBetter ? "red" : "green") : "green";

  const borderClass = (color: string) => color === "green" ? "border-green-500/30 bg-green-500/5" : "border-red-500/30 bg-red-500/5";
  const labelClass = (color: string) => color === "green" ? "text-green-400/60" : "text-red-400/60";
  const headerLabelClass = (color: string) => color === "green" ? "text-green-400/60" : "text-red-400/60";

  const demoOptions = allOptions.filter((o) => o.group === "demo");
  const historyOptions = allOptions.filter((o) => o.group === "history");

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold tracking-tight">AgentLens</h1>
          <span className="text-[10px] text-white/30 tracking-widest uppercase border border-white/10 rounded px-2 py-0.5">
            {isCustom ? "Session Comparison" : "A/B Comparison"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPicker(!showPicker)}
            className={`text-xs border rounded px-3 py-1.5 transition-colors cursor-pointer ${
              showPicker
                ? "text-blue-300 border-blue-500/50 bg-blue-500/10"
                : "text-blue-400/70 border-blue-500/20 hover:text-blue-300 hover:border-blue-500/40"
            }`}
          >
            Switch Datasets
          </button>
          <button
            onClick={onClose}
            className="text-xs text-white/50 hover:text-white border border-white/10 rounded px-3 py-1.5 transition-colors cursor-pointer"
          >
            Back to Dashboard
          </button>
        </div>
      </header>

      {/* Dataset Picker Strip */}
      {showPicker && (
        <div className="border-b border-white/10 bg-white/[0.02] px-6 py-4">
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-[10px] text-white/30 tracking-widest uppercase font-bold">Pick datasets to compare</span>
              {(loadingLeft || loadingRight) && (
                <span className="text-[10px] text-blue-400/60 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                  Loading...
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-6">
              {/* Session A picker */}
              <div>
                <label className="text-[10px] text-red-400/60 uppercase tracking-wider font-bold mb-1 block">Session A (Left)</label>
                <select
                  value={leftId}
                  onChange={(e) => handleLeftChange(e.target.value)}
                  className="w-full bg-black border border-white/10 rounded px-3 py-2 text-xs text-white/70 outline-none focus:border-blue-500/50 appearance-none cursor-pointer"
                >
                  <option value="" className="bg-black text-white/40">— Current —</option>
                  {demoOptions.length > 0 && (
                    <optgroup label="Demo Data" className="bg-black">
                      {demoOptions.map((o) => (
                        <option key={o.id} value={o.id} className="bg-black">{o.label}</option>
                      ))}
                    </optgroup>
                  )}
                  {historyOptions.length > 0 && (
                    <optgroup label="Session History" className="bg-black">
                      {historyOptions.map((o) => (
                        <option key={o.id} value={o.id} className="bg-black">{o.label}</option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </div>
              {/* Session B picker */}
              <div>
                <label className="text-[10px] text-green-400/60 uppercase tracking-wider font-bold mb-1 block">Session B (Right)</label>
                <select
                  value={rightId}
                  onChange={(e) => handleRightChange(e.target.value)}
                  className="w-full bg-black border border-white/10 rounded px-3 py-2 text-xs text-white/70 outline-none focus:border-blue-500/50 appearance-none cursor-pointer"
                >
                  <option value="" className="bg-black text-white/40">— Current —</option>
                  {demoOptions.length > 0 && (
                    <optgroup label="Demo Data" className="bg-black">
                      {demoOptions.map((o) => (
                        <option key={o.id} value={o.id} className="bg-black">{o.label}</option>
                      ))}
                    </optgroup>
                  )}
                  {historyOptions.length > 0 && (
                    <optgroup label="Session History" className="bg-black">
                      {historyOptions.map((o) => (
                        <option key={o.id} value={o.id} className="bg-black">{o.label}</option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="p-6 space-y-6 max-w-6xl mx-auto">
        {/* Hero: side-by-side health scores */}
        <div className="grid grid-cols-2 gap-6">
          <div className={`border rounded-lg p-6 text-center ${borderClass(leftColor)}`}>
            <div className={`text-[10px] tracking-widest uppercase mb-1 ${labelClass(leftColor)}`}>{leftLabel}</div>
            <MiniGauge score={u.health_score} size={120} />
            <div className="mt-3 flex items-center justify-center gap-2">
              <span className={`text-sm font-bold ${uFailed ? "text-red-400" : u.health_score >= 60 ? "text-green-400" : "text-white/60"}`}>
                {uFailed ? "TASK FAILED" : u.health_score >= 60 ? "TASK COMPLETED" : "DEGRADED"}
              </span>
            </div>
            <p className="text-[11px] text-white/30 mt-1">
              {uAnomalyCount} anomalies{uGuardrailCount > 0 ? `, ${uGuardrailCount} guardrails fired` : ", no intervention"}
            </p>
          </div>

          <div className={`border rounded-lg p-6 text-center ${borderClass(rightColor)}`}>
            <div className={`text-[10px] tracking-widest uppercase mb-1 ${labelClass(rightColor)}`}>{rightLabel}</div>
            <MiniGauge score={p.health_score} size={120} />
            <div className="mt-3 flex items-center justify-center gap-2">
              <span className={`text-sm font-bold ${p.health_score < 30 ? "text-red-400" : pSucceeded ? "text-green-400" : "text-white/60"}`}>
                {p.health_score < 30 ? "TASK FAILED" : pSucceeded ? "TASK COMPLETED" : "DEGRADED"}
              </span>
            </div>
            <p className="text-[11px] text-white/30 mt-1">
              {pAnomalyCount} anomalies{pGuardrailCount > 0 ? `, ${pGuardrailCount} guardrails fired` : ", no intervention"}
            </p>
          </div>
        </div>

        {/* Comparison Summary */}
        <div className="border border-blue-500/20 rounded-lg bg-blue-500/5 p-5">
          <h2 className="text-xs font-bold tracking-widest uppercase text-blue-400/70 mb-3">
            {isCustom ? "Comparison Summary" : "What AgentLens Did"}
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-mono font-bold text-blue-400">{Math.max(uGuardrailCount, pGuardrailCount)}</div>
              <div className="text-[10px] text-white/40 uppercase tracking-wider mt-1">Guardrails Fired</div>
              <div className="text-[10px] text-white/25 mt-0.5">
                {isCustom ? `Left: ${uGuardrailCount}, Right: ${pGuardrailCount}` : "Detected loops & error spirals"}
              </div>
            </div>
            <div className="text-center">
              <div className={`text-2xl font-mono font-bold ${healthDiff > 0 ? "text-green-400" : "text-white/50"}`}>
                {healthDiff > 0 ? (isCustom ? `${healthDiff}` : `+${healthDiff}`) : "0"}
              </div>
              <div className="text-[10px] text-white/40 uppercase tracking-wider mt-1">Health Delta</div>
              <div className="text-[10px] text-white/25 mt-0.5">
                {isCustom ? `${u.health_score} vs ${p.health_score}` : "Protected vs unprotected"}
              </div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-mono font-bold text-white/80">{stepsDiff}</div>
              <div className="text-[10px] text-white/40 uppercase tracking-wider mt-1">Steps Difference</div>
              <div className="text-[10px] text-white/25 mt-0.5">
                {u.steps.length} vs {p.steps.length}
              </div>
            </div>
          </div>
        </div>

        {/* Side-by-side timelines */}
        <div className="grid grid-cols-2 gap-6">
          <div className="border border-white/10 rounded-lg bg-white/[0.02] p-4">
            <MiniTimeline data={u} label={isCustom ? "Session A Timeline" : "Unprotected Timeline"} />
          </div>
          <div className="border border-white/10 rounded-lg bg-white/[0.02] p-4">
            <MiniTimeline data={p} label={isCustom ? "Session B Timeline" : "Protected Timeline"} />
          </div>
        </div>

        {/* Stats comparison table */}
        <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5">
          <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-4 text-center">Head-to-Head</h2>
          <div className="max-w-lg mx-auto">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 pb-2 mb-2 border-b border-white/10">
              <div className={`text-right text-[10px] uppercase tracking-wider font-bold ${headerLabelClass(leftColor)}`}>
                {isCustom ? "Session A" : "Unprotected"}
              </div>
              <div className="w-24" />
              <div className={`text-[10px] uppercase tracking-wider font-bold ${headerLabelClass(rightColor)}`}>
                {isCustom ? "Session B" : "Protected"}
              </div>
            </div>
            <StatRow
              label="Health"
              left={u.health_score}
              right={p.health_score}
              better={u.health_score > p.health_score ? "left" : u.health_score < p.health_score ? "right" : undefined}
            />
            <StatRow
              label="Steps"
              left={u.steps.length}
              right={p.steps.length}
              better={u.steps.length < p.steps.length ? "left" : u.steps.length > p.steps.length ? "right" : undefined}
            />
            <StatRow
              label="Tokens"
              left={`${(u.summary.total_tokens / 1000).toFixed(0)}k`}
              right={`${(p.summary.total_tokens / 1000).toFixed(0)}k`}
              better={u.summary.total_tokens < p.summary.total_tokens ? "left" : u.summary.total_tokens > p.summary.total_tokens ? "right" : undefined}
            />
            <StatRow
              label="Anomalies"
              left={uAnomalyCount}
              right={pAnomalyCount}
              better={uAnomalyCount < pAnomalyCount ? "left" : uAnomalyCount > pAnomalyCount ? "right" : undefined}
            />
            <StatRow label="Guards" left={uGuardrailCount} right={pGuardrailCount} />
            <StatRow
              label="Context Peak"
              left={`${Math.max(...u.steps.map((s) => s.trajectory_metrics.context_utilization_pct))}%`}
              right={`${Math.max(...p.steps.map((s) => s.trajectory_metrics.context_utilization_pct))}%`}
              better={
                Math.max(...u.steps.map((s) => s.trajectory_metrics.context_utilization_pct)) <
                Math.max(...p.steps.map((s) => s.trajectory_metrics.context_utilization_pct))
                  ? "left" : "right"
              }
            />
            <StatRow
              label="Outcome"
              left={uFailed ? "Failed" : u.health_score >= 60 ? "Completed" : "Degraded"}
              right={p.health_score < 30 ? "Failed" : pSucceeded ? "Completed" : "Degraded"}
              better={u.health_score > p.health_score ? "left" : u.health_score < p.health_score ? "right" : undefined}
            />
          </div>
        </div>

        {/* Narrative — only show for demo mode */}
        {!isCustom && (
          <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5">
            <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-3">The Story</h2>
            <div className="text-sm text-white/60 leading-relaxed space-y-2">
              <p>
                <span className="text-red-400 font-bold">Without AgentLens:</span> The agent attempted to refactor a Flask app to async.
                After {u.degradation_point?.step_id || 8} steps it entered an error spiral — repeatedly trying the same failing
                approach. By step {u.steps.length}, it had consumed{" "}
                {Math.max(...u.steps.map((s) => s.trajectory_metrics.context_utilization_pct))}% of its context window
                and was producing repetitive, low-quality output. The task was never completed.
              </p>
              <p>
                <span className="text-green-400 font-bold">With AgentLens:</span> The same task ran through AgentLens.
                At step {p.steps.find((s) => s.guardrail_injected)?.step_id || 11}, the proxy detected the beginning
                of a loop and injected a course-correction into the system prompt. The agent acknowledged the issue,
                changed its approach, and completed the task in {p.steps.length} steps with a health score of {p.health_score}.
              </p>
            </div>
          </div>
        )}

        {/* Auto narrative for custom compare */}
        {isCustom && (
          <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5">
            <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-3">Summary</h2>
            <div className="text-sm text-white/60 leading-relaxed space-y-2">
              <p>
                <span style={{ color: leftColor === "green" ? "#22c55e" : "#ef4444" }} className="font-bold">Session A</span> ran
                for {u.steps.length} steps with a final health of {u.health_score}.
                {uAnomalyCount > 0 ? ` ${uAnomalyCount} anomalies were detected.` : " No anomalies detected."}
                {uGuardrailCount > 0 ? ` ${uGuardrailCount} guardrails fired.` : ""}
                {u.session_id && <span className="text-white/20 ml-1">({u.session_id.slice(0, 24)})</span>}
              </p>
              <p>
                <span style={{ color: rightColor === "green" ? "#22c55e" : "#ef4444" }} className="font-bold">Session B</span> ran
                for {p.steps.length} steps with a final health of {p.health_score}.
                {pAnomalyCount > 0 ? ` ${pAnomalyCount} anomalies were detected.` : " No anomalies detected."}
                {pGuardrailCount > 0 ? ` ${pGuardrailCount} guardrails fired.` : ""}
                {p.session_id && <span className="text-white/20 ml-1">({p.session_id.slice(0, 24)})</span>}
              </p>
              {healthDiff > 0 && (
                <p className="text-white/40">
                  Health difference: <span className="text-white/70 font-mono">{healthDiff} points</span>.
                  {leftBetter
                    ? " Session A performed better."
                    : " Session B performed better."}
                </p>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
