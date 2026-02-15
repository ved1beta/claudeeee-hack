export interface ToolCall {
  name: string;
  input_summary: string;
}

export interface Step {
  schema_version?: string;
  session_id?: string;
  step_id: number;
  timestamp: string;
  request: {
    message_count: number;
    total_input_tokens: number;
    tools_provided: string[];
    system_prompt_tokens: number;
  };
  response: {
    output_tokens: number;
    stop_reason: string;
    tools_called: ToolCall[];
    text_summary: string;
  };
  trajectory_metrics: {
    context_utilization_pct: number;
    cumulative_tokens: number;
    context_window_max: number;
    step_duration_ms: number;
    files_touched: string[];
    unique_tools_this_session: number;
    repeated_file_reads: number;
  };
  model: string;
  guardrail_injected?: string | null;
}

export interface Anomaly {
  type: string;
  severity: string;
  step_id?: number;
  start_step?: number;
  end_step?: number;
  current_step?: number;
  [key: string]: unknown;
}

export interface SessionInfo {
  session_id: string;
  total_steps: number;
  active: boolean;
  started_at: string | null;
}

export interface HealthBreakdown {
  structural: { score: number; weight: number };
  memory: { score: number; weight: number };
  stability: { score: number; weight: number };
  diversity: { score: number; weight: number };
}

export interface DegradationPoint {
  step_id: number;
  health_at_point: number;
  message: string;
}

export interface GuardrailEvent {
  step: number;
  type: string;
  timestamp: number;
}

export interface Checkpoint {
  step_id: number;
  timestamp: number;
  message_count: number;
}

export interface PastSession {
  session_id: string;
  display_name?: string;
  started_at: string | null;
  total_steps: number;
  has_checkpoints: boolean;
}

export interface FixReport {
  degradation_step: number | null;
  failure_mode: string;
  confidence: number;
  root_cause_category: string;
  root_cause: string;
  recommendation: string;
  severity: string;
  narrative: string;
}

export interface AnalysisData {
  total_steps: number;
  health_score: number;
  health_breakdown?: HealthBreakdown;
  degradation_point?: DegradationPoint | null;
  session_id?: string;
  anomalies: {
    loops: Anomaly[];
    context_decay: Anomaly[];
    repetition: Anomaly[];
    error_spirals: Anomaly[];
  };
  steps: Step[];
  summary: {
    total_tokens: number;
    final_context_pct: number;
    total_tool_calls: number;
    total_duration_s: number;
  };
  guardrails_triggered?: GuardrailEvent[];
}
