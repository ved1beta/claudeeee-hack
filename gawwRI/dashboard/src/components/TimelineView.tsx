import type { Step, Anomaly, DegradationPoint } from "../types";
import AnomalyBadge from "./AnomalyBadge";

interface TimelineViewProps {
  steps: Step[];
  anomalies: {
    loops: Anomaly[];
    context_decay: Anomaly[];
    repetition: Anomaly[];
    error_spirals: Anomaly[];
  };
  selectedStep: number | null;
  onSelectStep: (stepId: number) => void;
  degradationPoint?: DegradationPoint | null;
}

function getStepColor(step: Step, anomalyType: string | null): string {
  // Guardrail-injected steps get blue
  if (step.guardrail_injected) return "#3b82f6";
  if (anomalyType === "LOOP" || anomalyType === "ERROR_SPIRAL" || anomalyType === "CONTEXT_ROT") {
    return "#ef4444";
  }
  if (anomalyType === "CONTEXT_DECAY" || anomalyType === "REPETITION") {
    return "#f59e0b";
  }
  const pct = step.trajectory_metrics.context_utilization_pct;
  if (pct > 70) return "#ef4444";
  if (pct > 40) return "#f59e0b";
  return "#22c55e";
}

function getStepAnomaly(stepId: number, anomalies: TimelineViewProps["anomalies"]): string | null {
  for (const a of anomalies.loops) {
    if (a.start_step && a.end_step && stepId >= a.start_step && stepId <= a.end_step) return "LOOP";
  }
  for (const a of anomalies.error_spirals) {
    if (a.start_step && a.current_step && stepId >= a.start_step && stepId <= a.current_step) return "ERROR_SPIRAL";
  }
  for (const a of anomalies.context_decay) {
    if (a.step_id === stepId) return a.type;
  }
  for (const a of anomalies.repetition) {
    if (a.step_id === stepId) return "REPETITION";
  }
  return null;
}

export default function TimelineView({ steps, anomalies, selectedStep, onSelectStep, degradationPoint }: TimelineViewProps) {
  return (
    <div className="border border-white/10 rounded-lg p-6 bg-white/[0.02]">
      <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-6">Trajectory Timeline</h2>
      <div className="overflow-x-auto pb-4">
        <div className="flex items-center gap-1 min-w-max px-2">
          {steps.map((step, i) => {
            const anomalyType = getStepAnomaly(step.step_id, anomalies);
            const color = getStepColor(step, anomalyType);
            const isSelected = selectedStep === step.step_id;

            return (
              <div key={step.step_id} className="flex items-center">
                <div className="relative flex flex-col items-center">
                  {step.guardrail_injected && (
                    <span className="relative group/guard">
                      <span className="text-[7px] px-1 py-0.5 rounded bg-blue-500/20 text-blue-400 font-bold mb-0.5 whitespace-nowrap cursor-help">
                        GUARD
                      </span>
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover/guard:block z-20 bg-black border border-blue-500/30 rounded px-2 py-1.5 text-[9px] text-blue-300/80 whitespace-nowrap shadow-lg">
                        {step.guardrail_injected === "LOOP"
                          ? "Agent was stuck in a loop — AgentLens injected a course correction"
                          : step.guardrail_injected === "ERROR_SPIRAL"
                          ? "Agent kept hitting errors — AgentLens told it to change approach"
                          : step.guardrail_injected === "CONTEXT_ROT"
                          ? "Context window nearly full — AgentLens prompted the agent to wrap up"
                          : `AgentLens intervened: ${step.guardrail_injected}`}
                      </span>
                    </span>
                  )}
                  {anomalyType && <AnomalyBadge type={anomalyType} />}
                  <button
                    onClick={() => onSelectStep(step.step_id)}
                    className={`w-8 h-8 rounded-full border-2 transition-all duration-200 flex items-center justify-center text-[10px] font-mono font-bold cursor-pointer
                      ${isSelected ? "scale-125 ring-2 ring-white/30" : "hover:scale-110"}
                      ${anomalyType ? "animate-pulse-red" : ""}
                    `}
                    style={{
                      borderColor: color,
                      backgroundColor: `${color}20`,
                      color: color,
                    }}
                  >
                    {step.step_id}
                  </button>
                  <span className="text-[8px] text-white/20 mt-1 font-mono">
                    {step.trajectory_metrics.context_utilization_pct}%
                  </span>
                  {degradationPoint && degradationPoint.step_id === step.step_id && (
                    <span className="text-[7px] text-red-400 mt-0.5 whitespace-nowrap font-bold">
                      DEGRADATION
                    </span>
                  )}
                </div>
                {i < steps.length - 1 && (
                  <div className="w-4 h-px bg-white/10 mx-0.5" />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
