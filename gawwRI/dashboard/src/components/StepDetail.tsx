import type { Step, Anomaly } from "../types";

interface StepDetailProps {
  step: Step;
  anomalies: Anomaly[];
  onClose: () => void;
}

export default function StepDetail({ step, anomalies, onClose }: StepDetailProps) {
  return (
    <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5 h-fit">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-medium tracking-widest uppercase text-white/40">
          Step {step.step_id}
        </h3>
        <button
          onClick={onClose}
          className="text-white/30 hover:text-white text-sm cursor-pointer"
        >
          &times;
        </button>
      </div>

      {step.guardrail_injected && (
        <div className="mb-4 p-3 border border-blue-500/30 rounded bg-blue-500/5">
          <div className="text-blue-400 text-xs font-bold">GUARDRAIL FIRED: {step.guardrail_injected}</div>
          <div className="text-blue-300/60 text-[10px] mt-1">
            {step.guardrail_injected === "LOOP"
              ? "The agent was repeating the same actions. AgentLens injected a system-prompt nudge telling it to stop and try a different approach."
              : step.guardrail_injected === "ERROR_SPIRAL"
              ? "The agent hit multiple consecutive errors. AgentLens told it to pause, reconsider, and change strategy."
              : step.guardrail_injected === "CONTEXT_ROT"
              ? "The context window was nearly exhausted. AgentLens prompted the agent to summarize progress and wrap up."
              : `AgentLens injected a course-correction: ${step.guardrail_injected}`}
          </div>
        </div>
      )}

      {anomalies.length > 0 && (
        <div className="mb-4 p-3 border border-red-500/30 rounded bg-red-500/5">
          {anomalies.map((a, i) => (
            <div key={i} className="text-red-400 text-xs font-mono">
              {a.type} &mdash; {a.severity}
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3 text-sm">
        <Row label="Timestamp" value={new Date(step.timestamp).toLocaleTimeString()} />
        <Row label="Input Tokens" value={step.request.total_input_tokens.toLocaleString()} />
        <Row label="Output Tokens" value={step.response.output_tokens.toLocaleString()} />
        <Row label="Duration" value={`${step.trajectory_metrics.step_duration_ms}ms`} />
        <Row label="Context Used" value={`${step.trajectory_metrics.context_utilization_pct}%`} />
        <Row label="Stop Reason" value={step.response.stop_reason} />

        {step.response.tools_called.length > 0 && (
          <div>
            <div className="text-white/40 text-xs mb-1">Tools Called</div>
            <div className="space-y-1">
              {step.response.tools_called.map((tc, i) => (
                <div key={i} className="font-mono text-xs bg-white/5 rounded px-2 py-1">
                  <span className="text-white/80">{tc.name}</span>
                  <span className="text-white/30 ml-2">{tc.input_summary.slice(0, 60)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="text-white/40 text-xs mb-1">Agent Output</div>
          <p className="text-white/60 text-xs leading-relaxed bg-white/5 rounded p-2">
            {step.response.text_summary || "—"}
          </p>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-white/40 text-xs">{label}</span>
      <span className="font-mono text-xs text-white/80">{value}</span>
    </div>
  );
}
