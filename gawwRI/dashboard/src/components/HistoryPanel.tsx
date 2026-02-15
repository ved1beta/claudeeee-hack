import { useState, useEffect } from "react";
import type { PastSession, AnalysisData, FixReport } from "../types";

const API = "http://localhost:8000";

interface PastSessionWithName extends PastSession {
  display_name?: string;
}

interface HistoryPanelProps {
  onLoadSession: (data: AnalysisData) => void;
  onCompare: (a: AnalysisData, b: AnalysisData) => void;
  onClose: () => void;
}

export default function HistoryPanel({ onLoadSession, onCompare, onClose }: HistoryPanelProps) {
  const [sessions, setSessions] = useState<PastSessionWithName[]>([]);
  const [loading, setLoading] = useState(true);
  const [fixReport, setFixReport] = useState<FixReport | null>(null);
  const [fixReportLoading, setFixReportLoading] = useState<string | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [compareSelection, setCompareSelection] = useState<string[]>([]);
  const [compareLoading, setCompareLoading] = useState(false);

  useEffect(() => {
    fetch(`${API}/history`)
      .then((r) => r.json())
      .then((d) => {
        setSessions(d.sessions || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const loadSession = async (sessionId: string) => {
    try {
      const r = await fetch(`${API}/history/${sessionId}`);
      if (r.ok) {
        const data: AnalysisData = await r.json();
        onLoadSession(data);
      }
    } catch { /* ignore */ }
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await fetch(`${API}/history/${sessionId}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } catch { /* ignore */ }
  };

  const generateFixReport = async (sessionId: string) => {
    setFixReportLoading(sessionId);
    try {
      const r = await fetch(`${API}/fix-report/${sessionId}`, { method: "POST" });
      if (r.ok) {
        const data = await r.json();
        setFixReport(data.fix_report);
      }
    } catch { /* ignore */ }
    setFixReportLoading(null);
  };

  const toggleCompareSelect = (sessionId: string) => {
    setCompareSelection((prev) => {
      if (prev.includes(sessionId)) return prev.filter((id) => id !== sessionId);
      if (prev.length >= 2) return [prev[1], sessionId]; // replace oldest
      return [...prev, sessionId];
    });
  };

  const runCompare = async () => {
    if (compareSelection.length !== 2) return;
    setCompareLoading(true);
    try {
      const [r1, r2] = await Promise.all(
        compareSelection.map((id) => fetch(`${API}/history/${id}`).then((r) => r.json()))
      );
      onCompare(r1 as AnalysisData, r2 as AnalysisData);
    } catch { /* ignore */ }
    setCompareLoading(false);
  };

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center">
      <div className="bg-[#0a0a0a] border border-white/10 rounded-lg w-[700px] max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h2 className="text-sm font-bold tracking-wider uppercase text-white/60">Session History</h2>
          <div className="flex items-center gap-2">
            {!compareMode ? (
              <button
                onClick={() => setCompareMode(true)}
                className="text-[10px] text-blue-400/70 hover:text-blue-300 border border-blue-500/20 rounded px-2 py-1 cursor-pointer"
              >
                Compare Two Sessions
              </button>
            ) : (
              <>
                <span className="text-[10px] text-blue-400/50">
                  {compareSelection.length}/2 selected
                </span>
                <button
                  onClick={runCompare}
                  disabled={compareSelection.length !== 2 || compareLoading}
                  className="text-[10px] text-blue-400 hover:text-blue-300 border border-blue-500/30 rounded px-2 py-1 cursor-pointer disabled:opacity-30 bg-blue-500/10"
                >
                  {compareLoading ? "Loading..." : "Compare"}
                </button>
                <button
                  onClick={() => { setCompareMode(false); setCompareSelection([]); }}
                  className="text-[10px] text-white/30 hover:text-white border border-white/10 rounded px-2 py-1 cursor-pointer"
                >
                  Cancel
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="text-white/30 hover:text-white text-sm cursor-pointer ml-2"
            >
              Close
            </button>
          </div>
        </div>

        {/* Compare hint */}
        {compareMode && (
          <div className="px-4 pt-3 pb-1">
            <p className="text-[10px] text-blue-400/40">Click two sessions to select them for side-by-side comparison. The first is shown on the left, the second on the right.</p>
          </div>
        )}

        {/* Session List */}
        <div className="p-4 space-y-2">
          {loading && <p className="text-white/30 text-xs">Loading...</p>}
          {!loading && sessions.length === 0 && (
            <p className="text-white/30 text-xs">No past sessions found. Run an agent through the proxy to create one.</p>
          )}

          {sessions.map((s) => {
            const isSelected = compareSelection.includes(s.session_id);
            const selIndex = compareSelection.indexOf(s.session_id);
            return (
              <div
                key={s.session_id}
                className={`border rounded p-3 flex items-center justify-between transition-colors ${
                  compareMode && isSelected
                    ? "border-blue-500/50 bg-blue-500/10"
                    : "border-white/10"
                } ${compareMode ? "cursor-pointer hover:border-blue-500/30" : ""}`}
                onClick={compareMode ? () => toggleCompareSelect(s.session_id) : undefined}
              >
                <div className="flex items-center gap-3">
                  {compareMode && (
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center text-[9px] font-bold ${
                      isSelected ? "border-blue-500 bg-blue-500/20 text-blue-400" : "border-white/20 text-white/20"
                    }`}>
                      {isSelected ? selIndex + 1 : ""}
                    </div>
                  )}
                  <div>
                    <div className="text-xs font-medium text-white/80">
                      {s.display_name || s.session_id.slice(0, 20)}
                    </div>
                    <div className="text-[10px] text-white/30 mt-0.5 font-mono">
                      {s.started_at ? new Date(s.started_at).toLocaleString() : "Unknown"} · {s.total_steps} steps
                      {s.has_checkpoints && " · checkpoints"}
                    </div>
                  </div>
                </div>
                {!compareMode && (
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => loadSession(s.session_id)}
                      className="text-[10px] text-white/50 hover:text-white border border-white/10 rounded px-2 py-1 cursor-pointer"
                    >
                      Load
                    </button>
                    <button
                      onClick={() => generateFixReport(s.session_id)}
                      disabled={fixReportLoading === s.session_id}
                      className="text-[10px] text-white/50 hover:text-white border border-white/10 rounded px-2 py-1 cursor-pointer disabled:opacity-30"
                      title="Uses Claude to analyze the session trajectory, diagnose failure patterns (loops, error cascades, context exhaustion), and recommend fixes"
                    >
                      {fixReportLoading === s.session_id ? "Analyzing..." : "Fix Report"}
                    </button>
                    <button
                      onClick={() => deleteSession(s.session_id)}
                      className="text-[10px] text-red-400/50 hover:text-red-400 border border-red-500/10 rounded px-2 py-1 cursor-pointer"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Fix Report */}
        {fixReport && (
          <div className="p-4 border-t border-white/10">
            <h3 className="text-xs font-bold tracking-wider uppercase text-white/60 mb-1">Fix Report</h3>
            <p className="text-[10px] text-white/25 mb-3">AI-generated diagnosis of what went wrong and how to fix it</p>
            <div className="space-y-2">
              <div className="flex gap-2">
                <span className="text-[10px] px-2 py-0.5 rounded bg-red-500/20 text-red-400 font-bold">
                  {fixReport.failure_mode}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-white/40">
                  {fixReport.severity}
                </span>
              </div>
              {fixReport.narrative && (
                <p className="text-xs text-white/50">{fixReport.narrative}</p>
              )}
              {fixReport.root_cause && (
                <div className="border border-white/10 rounded p-2 bg-white/[0.02]">
                  <div className="text-[9px] text-white/30 uppercase tracking-wider mb-1">Root Cause</div>
                  <p className="text-xs text-white/60">{fixReport.root_cause}</p>
                </div>
              )}
              {fixReport.recommendation && (
                <div className="border border-green-500/20 rounded p-2 bg-green-500/5">
                  <div className="text-[9px] text-green-400/60 uppercase tracking-wider mb-1">Recommendation</div>
                  <p className="text-xs text-green-400/80">{fixReport.recommendation}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
