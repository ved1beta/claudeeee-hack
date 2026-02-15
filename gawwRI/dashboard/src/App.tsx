import { useState, useCallback, useEffect, useRef } from "react";
import TimelineView from "./components/TimelineView";
import MetricsPanel from "./components/MetricsPanel";
import StepDetail from "./components/StepDetail";
import TrajectoryHeatmap from "./components/TrajectoryHeatmap";
import HistoryPanel from "./components/HistoryPanel";
import CompareView from "./components/CompareView";
import type { DatasetOption } from "./components/CompareView";
import sampleData from "./data/sample.json";
import demoUnprotected from "./data/demo_unprotected.json";
import demoProtected from "./data/demo_protected.json";
import type { AnalysisData, Anomaly, Step, SessionInfo } from "./types";
import "./App.css";

// Pre-built demo datasets available for comparison picker
const DEMO_DATASETS: DatasetOption[] = [
  {
    id: "demo:unprotected",
    label: "Demo — Unprotected (15 steps, FastAPI task)",
    group: "demo",
    data: demoUnprotected as AnalysisData,
  },
  {
    id: "demo:protected",
    label: "Demo — Protected (2 steps, FastAPI task)",
    group: "demo",
    data: demoProtected as AnalysisData,
  },
  {
    id: "demo:sample",
    label: "Sample Trajectory (full analysis)",
    group: "demo",
    data: sampleData as AnalysisData,
  },
];

const API = "http://localhost:8000";

function getAnomaliesForStep(stepId: number, anomalies: AnalysisData["anomalies"]): Anomaly[] {
  const result: Anomaly[] = [];
  for (const a of anomalies.loops) {
    if (a.start_step && a.end_step && stepId >= a.start_step && stepId <= a.end_step) result.push(a);
  }
  for (const a of anomalies.context_decay) {
    if (a.step_id === stepId) result.push(a);
  }
  for (const a of anomalies.repetition) {
    if (a.step_id === stepId) result.push(a);
  }
  for (const a of anomalies.error_spirals) {
    if (a.start_step && a.current_step && stepId >= a.start_step && stepId <= a.current_step) result.push(a);
  }
  return result;
}

function buildFallbackAnalysis(steps: Step[]): AnalysisData {
  const last = steps[steps.length - 1];
  return {
    total_steps: steps.length,
    health_score: 100,
    anomalies: { loops: [], context_decay: [], repetition: [], error_spirals: [] },
    steps,
    summary: {
      total_tokens: last?.trajectory_metrics?.cumulative_tokens || 0,
      final_context_pct: last?.trajectory_metrics?.context_utilization_pct || 0,
      total_tool_calls: steps.reduce((sum, s) => sum + (s.response?.tools_called?.length || 0), 0),
      total_duration_s: steps.reduce((sum, s) => sum + ((s.trajectory_metrics?.step_duration_ms || 0) / 1000), 0),
    },
  };
}

type Mode = "sample" | "live" | "upload" | "history" | "compare";

export default function App() {
  const emptyData: AnalysisData = {
    total_steps: 0,
    health_score: 100,
    anomalies: { loops: [], context_decay: [], repetition: [], error_spirals: [] },
    steps: [],
    summary: { total_tokens: 0, final_context_pct: 0, total_tool_calls: 0, total_duration_s: 0 },
  };
  const [data, setData] = useState<AnalysisData>(emptyData);
  const [selectedStep, setSelectedStep] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("sample");
  const [serverOnline, setServerOnline] = useState(false);
  const [liveStepCount, setLiveStepCount] = useState(0);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showCompare, setShowCompare] = useState(false);
  const [compareData, setCompareData] = useState<{ a: AnalysisData; b: AnalysisData } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Comparison runner state
  const [promptInput, setPromptInput] = useState("");
  const [repoUrlInput, setRepoUrlInput] = useState("");
  const [isRunningComparison, setIsRunningComparison] = useState(false);
  const [comparisonId, setComparisonId] = useState<string | null>(null);
  const [comparisonProgress, setComparisonProgress] = useState<{
    unprotected_steps: number;
    protected_steps: number;
    status: string;
    error?: string;
  } | null>(null);
  const compPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Check server status on mount
  useEffect(() => {
    fetch(`${API}/`)
      .then((r) => { if (r.ok) setServerOnline(true); })
      .catch(() => setServerOnline(false));
  }, []);

  // Poll /latest when in live mode
  useEffect(() => {
    if (mode !== "live") {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }

    const poll = async () => {
      try {
        // Fetch session list
        const sr = await fetch(`${API}/sessions`);
        if (sr.ok) {
          const sd = await sr.json();
          setSessions(sd.sessions || []);
        }
        // Fetch analysis for active session
        const url = activeSessionId
          ? `${API}/latest?session_id=${activeSessionId}`
          : `${API}/latest`;
        const r = await fetch(url);
        if (r.ok) {
          const d: AnalysisData = await r.json();
          if (d.total_steps > 0 && d.total_steps !== liveStepCount) {
            setData(d);
            setLiveStepCount(d.total_steps);
            if (d.session_id) setActiveSessionId(d.session_id);
          }
        }
      } catch { /* server down */ }
    };

    poll(); // immediate first fetch
    pollRef.current = setInterval(poll, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [mode, liveStepCount, activeSessionId]);

  const startLive = useCallback(async () => {
    setLiveStepCount(0);
    setMode("live");
    setSelectedStep(null);
  }, []);

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      if (serverOnline) {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(`${API}/analyze`, { method: "POST", body: fd });
        if (r.ok) {
          setData(await r.json());
          setMode("upload");
          setSelectedStep(null);
          e.target.value = "";
          return;
        }
      }

      const text = await file.text();
      const lines = text.trim().split("\n");
      const steps = lines.map((line) => JSON.parse(line)) as Step[];
      setData(buildFallbackAnalysis(steps));
      setMode("upload");
      setSelectedStep(null);
    } catch {
      alert("Could not parse file. Ensure it's valid JSONL.");
    }
    e.target.value = "";
  }, [serverOnline]);

  const loadSample = useCallback(() => {
    setData(sampleData as AnalysisData);
    setMode("sample");
    setSelectedStep(null);
  }, []);

  const handleLoadHistorySession = useCallback((analysisData: AnalysisData) => {
    setData(analysisData);
    setMode("history");
    setSelectedStep(null);
    setShowHistory(false);
  }, []);

  const handleCompare = useCallback((a: AnalysisData, b: AnalysisData) => {
    setCompareData({ a, b });
    setShowCompare(true);
    setShowHistory(false);
  }, []);

  // Start a comparison run
  const startComparison = useCallback(async () => {
    if (!promptInput.trim()) return;
    setIsRunningComparison(true);
    setComparisonProgress({ unprotected_steps: 0, protected_steps: 0, status: "starting" });
    try {
      const r = await fetch(`${API}/run-comparison`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: promptInput.trim(), repo_url: repoUrlInput.trim() || undefined }),
      });
      if (!r.ok) throw new Error(`Server error: ${r.status}`);
      const { comparison_id } = await r.json();
      setComparisonId(comparison_id);
    } catch (err) {
      setIsRunningComparison(false);
      setComparisonProgress(null);
      alert(`Failed to start comparison: ${err}`);
    }
  }, [promptInput, repoUrlInput]);

  // Poll comparison status
  useEffect(() => {
    if (!comparisonId || !isRunningComparison) {
      if (compPollRef.current) clearInterval(compPollRef.current);
      return;
    }

    const poll = async () => {
      try {
        const r = await fetch(`${API}/comparison/${comparisonId}`);
        if (!r.ok) return;
        const d = await r.json();
        setComparisonProgress({
          unprotected_steps: d.unprotected?.steps || 0,
          protected_steps: d.protected?.steps || 0,
          status: d.status,
          error: d.error,
        });

        if (d.status === "completed" && d.unprotected_data && d.protected_data) {
          // Auto-open CompareView with results
          setCompareData({ a: d.unprotected_data, b: d.protected_data });
          setShowCompare(true);
          setIsRunningComparison(false);
          setComparisonId(null);
          if (compPollRef.current) clearInterval(compPollRef.current);
        } else if (d.status === "error") {
          setIsRunningComparison(false);
          setComparisonId(null);
          if (compPollRef.current) clearInterval(compPollRef.current);
        }
      } catch { /* server down */ }
    };

    poll();
    compPollRef.current = setInterval(poll, 2000);
    return () => { if (compPollRef.current) clearInterval(compPollRef.current); };
  }, [comparisonId, isRunningComparison]);

  const selected = selectedStep ? data.steps.find((s) => s.step_id === selectedStep) : null;

  // Count guardrails
  const guardrailCount = data.guardrails_triggered?.length || data.steps.filter((s) => s.guardrail_injected).length;

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold tracking-tight">AgentLens</h1>
          <span className="text-[10px] text-white/30 tracking-widest uppercase border border-white/10 rounded px-2 py-0.5">
            Detect &middot; Prevent &middot; Recover
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Server status */}
          <span className="flex items-center gap-1.5 text-[10px] text-white/30 mr-2">
            <span className={`w-1.5 h-1.5 rounded-full ${serverOnline ? "bg-green-500" : "bg-red-500"}`} />
            {serverOnline ? "Server" : "Offline"}
          </span>

          {/* Session selector (live mode with multiple sessions) */}
          {mode === "live" && sessions.length > 1 && (
            <select
              value={activeSessionId || ""}
              onChange={(e) => { setActiveSessionId(e.target.value); setLiveStepCount(0); }}
              className="text-[10px] bg-transparent border border-white/10 rounded px-2 py-1 text-white/60 outline-none"
            >
              {sessions.map((s) => (
                <option key={s.session_id} value={s.session_id} className="bg-black">
                  {s.session_id.slice(0, 8)}... ({s.total_steps} steps){s.active ? " *" : ""}
                </option>
              ))}
            </select>
          )}

          {/* Mode indicator */}
          {mode === "live" && (
            <span className="flex items-center gap-1.5 text-[10px] text-red-400 border border-red-500/30 rounded px-2 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              LIVE &middot; {data.total_steps} steps
              {guardrailCount > 0 && (
                <span className="text-blue-400 ml-1">&middot; {guardrailCount} guards</span>
              )}
            </span>
          )}

          {/* Actions */}
          {serverOnline && mode !== "live" && (
            <button
              onClick={startLive}
              className="text-xs text-white/50 hover:text-white border border-white/10 rounded px-3 py-1.5 transition-colors cursor-pointer"
            >
              Go Live
            </button>
          )}
          {mode === "live" && (
            <button
              onClick={() => setMode("upload")}
              className="text-xs text-white/50 hover:text-white border border-white/10 rounded px-3 py-1.5 transition-colors cursor-pointer"
            >
              Stop
            </button>
          )}
          {serverOnline && (
            <button
              onClick={() => setShowHistory(true)}
              className="text-xs text-white/50 hover:text-white border border-white/10 rounded px-3 py-1.5 transition-colors cursor-pointer"
            >
              History
            </button>
          )}
          <button
            onClick={() => setShowCompare(true)}
            className="text-xs text-blue-400/80 hover:text-blue-300 border border-blue-500/30 rounded px-3 py-1.5 transition-colors cursor-pointer bg-blue-500/5"
          >
            A/B Demo
          </button>
          <label className="cursor-pointer text-xs text-white/50 hover:text-white border border-white/10 rounded px-3 py-1.5 transition-colors">
            Upload .jsonl
            <input type="file" accept=".jsonl,.json" onChange={handleFileUpload} className="hidden" />
          </label>
          {mode !== "sample" && (
            <button
              onClick={loadSample}
              className="text-xs text-white/50 hover:text-white border border-white/10 rounded px-3 py-1.5 transition-colors cursor-pointer"
            >
              Sample
            </button>
          )}
        </div>
      </header>

      {data.total_steps === 0 ? (
        <div className="flex flex-col items-center justify-center h-[60vh] text-white/30">
          <div className="text-center max-w-xl space-y-4">
            <h2 className="text-xl text-white/70 font-semibold">AI agents fail silently.</h2>
            <p className="text-sm text-white/40 leading-relaxed">
              AgentLens sits between your agent and the LLM API. It detects loops, error spirals, and context decay
              in real time — then injects guardrails to get the agent back on track.
            </p>
            <div className="flex items-center justify-center gap-6 text-[11px] text-white/30 pt-2">
              <div className="text-center">
                <div className="text-white/50 font-bold text-sm">Detect</div>
                <div>loops, spirals, drift</div>
              </div>
              <div className="text-white/10">|</div>
              <div className="text-center">
                <div className="text-white/50 font-bold text-sm">Prevent</div>
                <div>wasted tokens & time</div>
              </div>
              <div className="text-white/10">|</div>
              <div className="text-center">
                <div className="text-white/50 font-bold text-sm">Recover</div>
                <div>guardrail injection</div>
              </div>
            </div>

            {/* Comparison Runner */}
            {isRunningComparison ? (
              <div className="pt-6 space-y-3">
                <div className="flex items-center justify-center gap-2 text-sm text-white/50">
                  <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                  Running A/B Comparison...
                </div>
                <div className="bg-white/5 border border-white/10 rounded-lg p-4 text-left space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-red-400">Unprotected</span>
                    <span className="text-white/40 font-mono">{comparisonProgress?.unprotected_steps || 0} steps</span>
                  </div>
                  <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-red-500/60 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, (comparisonProgress?.unprotected_steps || 0) * 3.3)}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs pt-1">
                    <span className="text-green-400">Protected (AgentLens)</span>
                    <span className="text-white/40 font-mono">{comparisonProgress?.protected_steps || 0} steps</span>
                  </div>
                  <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500/60 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, (comparisonProgress?.protected_steps || 0) * 3.3)}%` }}
                    />
                  </div>
                  {comparisonProgress?.error && (
                    <p className="text-xs text-red-400 pt-1">{comparisonProgress.error}</p>
                  )}
                </div>
                <p className="text-[10px] text-white/20">Both agents are running the same task — one with AgentLens optimizations, one without.</p>
              </div>
            ) : (
              <div className="pt-6 space-y-3">
                <div className="text-xs text-white/40 font-medium uppercase tracking-wider">Run A/B Comparison</div>
                <div className="bg-white/5 border border-white/10 rounded-lg p-4 space-y-3">
                  <textarea
                    value={promptInput}
                    onChange={(e) => setPromptInput(e.target.value)}
                    placeholder="Describe a coding task for the agent... e.g. 'Fix the NaN handling bug in tensor reduction operations'"
                    className="w-full bg-transparent border border-white/10 rounded-md px-3 py-2 text-sm text-white/80 placeholder-white/20 outline-none focus:border-blue-500/50 resize-none"
                    rows={3}
                  />
                  <input
                    value={repoUrlInput}
                    onChange={(e) => setRepoUrlInput(e.target.value)}
                    placeholder="Git repo URL (optional) — e.g. https://github.com/tinygrad/tinygrad"
                    className="w-full bg-transparent border border-white/10 rounded-md px-3 py-2 text-xs text-white/60 placeholder-white/15 outline-none focus:border-blue-500/50"
                  />
                  <button
                    onClick={startComparison}
                    disabled={!promptInput.trim() || !serverOnline}
                    className="w-full py-2 rounded-md text-sm font-medium transition-all cursor-pointer
                      disabled:opacity-30 disabled:cursor-not-allowed
                      bg-blue-600/20 border border-blue-500/30 text-blue-300 hover:bg-blue-600/30 hover:border-blue-500/50"
                  >
                    Run A/B Comparison
                  </button>
                </div>
                <p className="text-[10px] text-white/20">
                  Spawns two agents: one unprotected, one with loop detection, error spiral guards, context compacting, and tool validation.
                </p>
              </div>
            )}

            {mode === "live" ? (
              <p className="text-xs text-white/25 pt-2">Waiting for agent to start...</p>
            ) : !isRunningComparison && (
              <div className="pt-2 space-y-1">
                <p className="text-[10px] text-white/20">Or set <code className="text-white/40 bg-white/5 px-1 py-0.5 rounded text-[10px]">ANTHROPIC_BASE_URL=http://localhost:8000/proxy/v1</code> to monitor your own agent</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <main className="p-6 space-y-4">
          {/* Session ID bar */}
          {data.session_id && (
            <div className="text-[10px] text-white/20 font-mono">
              Session: {data.session_id}
              {mode === "history" && " (from history)"}
            </div>
          )}

          <TimelineView
            steps={data.steps}
            anomalies={data.anomalies}
            selectedStep={selectedStep}
            onSelectStep={setSelectedStep}
            degradationPoint={data.degradation_point}
          />
          <TrajectoryHeatmap data={data} />
          <div className={`grid gap-4 ${selected ? "grid-cols-[1fr_350px]" : "grid-cols-1"}`}>
            <MetricsPanel data={data} />
            {selected && (
              <StepDetail
                step={selected}
                anomalies={getAnomaliesForStep(selected.step_id, data.anomalies)}
                onClose={() => setSelectedStep(null)}
              />
            )}
          </div>
        </main>
      )}

      {/* History Panel Modal */}
      {showHistory && (
        <HistoryPanel
          onLoadSession={handleLoadHistorySession}
          onCompare={handleCompare}
          onClose={() => setShowHistory(false)}
        />
      )}

      {/* A/B Comparison View */}
      {showCompare && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <CompareView
            unprotected={compareData?.a || (demoUnprotected as AnalysisData)}
            protected_={compareData?.b || (demoProtected as AnalysisData)}
            onClose={() => { setShowCompare(false); setCompareData(null); }}
            isCustomCompare={!!compareData}
            demoDatasets={DEMO_DATASETS}
            serverOnline={serverOnline}
          />
        </div>
      )}
    </div>
  );
}
