interface AnomalyBadgeProps {
  type: string;
}

const LABELS: Record<string, string> = {
  LOOP: "LOOP",
  CONTEXT_ROT: "CTX ROT",
  CONTEXT_DECAY: "CTX DECAY",
  REPETITION: "REPEAT",
  ERROR_SPIRAL: "ERR SPIRAL",
};

const TOOLTIPS: Record<string, string> = {
  LOOP: "Agent is repeating the same actions without progress",
  CONTEXT_ROT: "Context window is nearly full, output quality will degrade",
  CONTEXT_DECAY: "Context utilization is growing fast, approaching limits",
  REPETITION: "Agent is re-reading files or re-running commands it already did",
  ERROR_SPIRAL: "Agent is hitting consecutive errors and not recovering",
};

export default function AnomalyBadge({ type }: AnomalyBadgeProps) {
  return (
    <span className="absolute -top-6 left-1/2 -translate-x-1/2 group/badge">
      <span className="whitespace-nowrap text-[9px] font-bold tracking-wider uppercase bg-red-500/20 text-red-400 border border-red-500/40 rounded px-1.5 py-0.5 cursor-help">
        {LABELS[type] || type}
      </span>
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover/badge:block z-20 bg-black border border-red-500/30 rounded px-2 py-1.5 text-[9px] text-red-300/80 whitespace-nowrap shadow-lg">
        {TOOLTIPS[type] || type}
      </span>
    </span>
  );
}
