import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()


def analyze_trajectory_with_claude(trajectory_data):
    client = anthropic.Anthropic()

    summary = {
        "total_steps": trajectory_data["total_steps"],
        "health_score": trajectory_data["health_score"],
        "health_breakdown": trajectory_data.get("health_breakdown"),
        "degradation_point": trajectory_data.get("degradation_point"),
        "anomalies": {
            k: len(v) for k, v in trajectory_data["anomalies"].items()
        },
        "anomaly_details": {
            k: v[:3] for k, v in trajectory_data["anomalies"].items() if v
        },
        "step_summaries": [
            {
                "step": s["step_id"],
                "tools": [t["name"] for t in s.get("response", {}).get("tools_called", [])],
                "text": s.get("response", {}).get("text_summary", "")[:150],
                "context_pct": s.get("trajectory_metrics", {}).get("context_utilization_pct", 0),
            }
            for s in trajectory_data["steps"]
        ],
    }

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""You are an AI agent debugging expert. Analyze this agent trajectory data and produce a structured diagnosis.

Trajectory data:
{json.dumps(summary, indent=2)}

Respond ONLY with valid JSON (no markdown, no explanation outside JSON). Use this exact schema:
{{
  "degradation_step": <int or null — first step where things went wrong>,
  "failure_mode": "<one of: LOOP_LOCK | CONTEXT_EXHAUSTION | ERROR_CASCADE | TUNNEL_VISION | HEALTHY>",
  "confidence": <float 0.0-1.0>,
  "root_cause_category": "<one of: STUCK_ON_WRONG_APPROACH | MISSING_CONTEXT | TOOL_MISUSE | ENVIRONMENT_FAILURE | SCOPE_CREEP | NONE>",
  "root_cause": "<1-2 sentence specific explanation>",
  "recommendation": "<1-2 sentence actionable fix>",
  "severity": "<CRITICAL | HIGH | MEDIUM | LOW>",
  "narrative": "<2-3 sentence human-readable summary of what happened>"
}}"""
        }],
    )
    return response.content[0].text


def generate_corrective_prompt(analysis_data: dict, from_step: int) -> str:
    """
    Generate a corrective strategy prompt for branching from a checkpoint.
    Analyzes what went wrong after from_step and produces an instruction
    to inject into the new session to prevent the same failure.
    """
    client = anthropic.Anthropic()

    summary = {
        "health_score": analysis_data.get("health_score"),
        "anomalies": {
            k: len(v) for k, v in analysis_data.get("anomalies", {}).items()
        },
        "anomaly_details": {
            k: v[:3] for k, v in analysis_data.get("anomalies", {}).items() if v
        },
        "step_summaries": [
            {
                "step": s["step_id"],
                "tools": [t["name"] for t in s.get("response", {}).get("tools_called", [])],
                "text": s.get("response", {}).get("text_summary", "")[:100],
            }
            for s in analysis_data.get("steps", [])
        ],
    }

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""You are an AI agent debugging expert. An agent went off the rails after step {from_step}.

Here is the analysis of what happened AFTER step {from_step}:
{json.dumps(summary, indent=2)}

Generate a single, clear corrective instruction that should be injected at step {from_step}
to prevent this failure pattern. Be specific and actionable. The instruction should tell the
agent what to do differently without revealing that it previously failed.

Output ONLY the instruction text, nothing else. Keep it under 3 sentences."""
        }],
    )
    return response.content[0].text


if __name__ == "__main__":
    with open("analysis.json") as f:
        data = json.load(f)

    result = analyze_trajectory_with_claude(data)
    print(result)

    with open("meta_analysis.json", "w") as f:
        f.write(result)
    print("\nSaved to meta_analysis.json")
