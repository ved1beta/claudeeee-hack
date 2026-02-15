import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, ReferenceLine,
} from "recharts";
import type { AnalysisData } from "../types";

interface MetricsPanelProps {
  data: AnalysisData;
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

function HealthGauge({ score }: { score: number }) {
  const color = getHealthColor(score);
  const radius = 60;
  const circumference = Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="80" viewBox="0 0 140 80">
        <path
          d="M 10 75 A 60 60 0 0 1 130 75"
          fill="none"
          stroke="#1a1a1a"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d="M 10 75 A 60 60 0 0 1 130 75"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={`${offset}`}
          style={{ transition: "stroke-dashoffset 1s ease" }}
        />
        <text x="70" y="65" textAnchor="middle" fill={color} fontSize="28" fontWeight="bold" fontFamily="monospace">
          {score}
        </text>
      </svg>
      <span className="text-xs tracking-widest font-bold mt-1" style={{ color }}>
        {getHealthLabel(score)}
      </span>
    </div>
  );
}

export default function MetricsPanel({ data }: MetricsPanelProps) {
  const contextData = data.steps.map((s) => ({
    step: s.step_id,
    utilization: s.trajectory_metrics.context_utilization_pct,
  }));

  const toolCounts: Record<string, number> = {};
  for (const step of data.steps) {
    for (const tc of step.response.tools_called) {
      toolCounts[tc.name] = (toolCounts[tc.name] || 0) + 1;
    }
  }
  const toolData = Object.entries(toolCounts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);

  return (
    <div className="space-y-4">
      {/* Health + Summary */}
      <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5">
        <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-4">Health Score</h2>
        <HealthGauge score={data.health_score} />
        <div className="grid grid-cols-2 gap-3 mt-4 text-center">
          <Stat label="Steps" value={data.total_steps} />
          <Stat label="Total Tokens" value={`${(data.summary.total_tokens / 1000).toFixed(0)}k`} />
          <Stat label="Tool Calls" value={data.summary.total_tool_calls} />
          <Stat label="Duration" value={`${data.summary.total_duration_s.toFixed(0)}s`} />
        </div>

        {/* Health Breakdown */}
        {data.health_breakdown && (
          <div className="mt-4 space-y-2">
            <h3 className="text-[10px] text-white/30 uppercase tracking-wider">Score Breakdown</h3>
            {(["structural", "memory", "stability", "diversity"] as const).map((key) => {
              const comp = data.health_breakdown![key];
              const barColor = comp.score >= 70 ? "#22c55e" : comp.score >= 40 ? "#f59e0b" : "#ef4444";
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-[10px] text-white/40 w-16 font-mono">{key}</span>
                  <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${comp.score}%`, backgroundColor: barColor }}
                    />
                  </div>
                  <span className="text-[10px] text-white/50 w-8 text-right font-mono">{comp.score}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Degradation Point */}
        {data.degradation_point && (
          <div className="mt-3 border border-red-500/30 rounded px-3 py-2 bg-red-500/5">
            <div className="text-[10px] text-red-400 font-bold tracking-wider uppercase">Degradation Begins</div>
            <div className="text-xs text-white/60 mt-0.5">
              Step {data.degradation_point.step_id} — health dropped to {data.degradation_point.health_at_point}
            </div>
          </div>
        )}
      </div>

      {/* Context Budget Chart */}
      <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5">
        <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-4">Context Budget</h2>
        <ResponsiveContainer width="100%" height={160}>
          <AreaChart data={contextData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" />
            <XAxis dataKey="step" tick={{ fill: "#666", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "#1a1a1a" }} />
            <YAxis tick={{ fill: "#666", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "#1a1a1a" }} domain={[0, 100]} />
            <Tooltip
              contentStyle={{ background: "#111", border: "1px solid #222", borderRadius: 6, fontSize: 12 }}
              labelStyle={{ color: "#888" }}
            />
            <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" strokeOpacity={0.5} />
            <defs>
              <linearGradient id="contextGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                <stop offset="50%" stopColor="#f59e0b" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#22c55e" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <Area type="monotone" dataKey="utilization" stroke="#fff" strokeWidth={1.5} fill="url(#contextGradient)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Tool Distribution */}
      <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5">
        <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-4">Tool Distribution</h2>
        <ResponsiveContainer width="100%" height={toolData.length * 32 + 10}>
          <BarChart data={toolData} layout="vertical" margin={{ left: 60 }}>
            <XAxis type="number" tick={{ fill: "#666", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "#1a1a1a" }} />
            <YAxis type="category" dataKey="name" tick={{ fill: "#999", fontSize: 11, fontFamily: "monospace" }} tickLine={false} axisLine={false} width={70} />
            <Tooltip
              contentStyle={{ background: "#111", border: "1px solid #222", borderRadius: 6, fontSize: 12 }}
            />
            <Bar dataKey="count" radius={[0, 3, 3, 0]} barSize={16}>
              {toolData.map((_, index) => (
                <Cell key={index} fill={index === 0 ? "#fff" : "#444"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="font-mono text-lg text-white/90">{value}</div>
      <div className="text-[10px] text-white/30 uppercase tracking-wider">{label}</div>
    </div>
  );
}
