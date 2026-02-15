import type { AnalysisData, Anomaly } from "../types";

interface HeatmapProps {
  data: AnalysisData;
}

const ANOMALY_TYPES = ["LOOP", "CONTEXT_ROT", "CONTEXT_DECAY", "REPETITION", "ERROR_SPIRAL"] as const;

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#ef4444",
  HIGH: "#f97316",
  MEDIUM: "#f59e0b",
  LOW: "#22c55e",
};

function getAnomalyAtStep(stepId: number, type: string, anomalies: AnalysisData["anomalies"]): Anomaly | null {
  const all: Anomaly[] = [
    ...anomalies.loops,
    ...anomalies.context_decay,
    ...anomalies.repetition,
    ...anomalies.error_spirals,
  ];

  for (const a of all) {
    if (a.type !== type) continue;
    if (a.step_id === stepId) return a;
    if (a.start_step && a.end_step && stepId >= a.start_step && stepId <= a.end_step) return a;
    if (a.start_step && a.current_step && stepId >= a.start_step && stepId <= a.current_step) return a;
  }
  return null;
}

export default function TrajectoryHeatmap({ data }: HeatmapProps) {
  const cellSize = 18;
  const labelWidth = 100;

  return (
    <div className="border border-white/10 rounded-lg bg-white/[0.02] p-5">
      <h2 className="text-xs font-medium tracking-widest uppercase text-white/40 mb-4">Anomaly Heatmap</h2>
      <div className="overflow-x-auto">
        <div style={{ minWidth: data.steps.length * (cellSize + 2) + labelWidth }}>
          {/* Step numbers header */}
          <div className="flex items-center mb-1" style={{ paddingLeft: labelWidth }}>
            {data.steps.map((s) => (
              <div
                key={s.step_id}
                className="text-[8px] text-white/20 text-center"
                style={{ width: cellSize, marginRight: 2 }}
              >
                {s.step_id % 5 === 0 || s.step_id === 1 ? s.step_id : ""}
              </div>
            ))}
          </div>

          {/* Rows: one per anomaly type */}
          {ANOMALY_TYPES.map((type) => (
            <div key={type} className="flex items-center mb-[2px]">
              <div
                className="text-[9px] text-white/40 font-mono shrink-0 pr-2"
                style={{ width: labelWidth }}
              >
                {type.replace("_", " ")}
              </div>
              {data.steps.map((s) => {
                const anomaly = getAnomalyAtStep(s.step_id, type, data.anomalies);
                const color = anomaly ? SEVERITY_COLORS[anomaly.severity] || "#333" : "#111";
                return (
                  <div
                    key={s.step_id}
                    title={anomaly ? `${type} — ${anomaly.severity}` : ""}
                    style={{
                      width: cellSize,
                      height: cellSize,
                      marginRight: 2,
                      backgroundColor: color,
                      opacity: anomaly ? 0.85 : 0.3,
                      borderRadius: 2,
                    }}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mt-3">
        {Object.entries(SEVERITY_COLORS).map(([label, color]) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-[9px] text-white/30">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
