"""
AgentLens Proxy Core — step builder, SSE stream accumulator, guardrail checker.

This module provides the logic for the transparent proxy that sits between
Claude Code (or any Anthropic SDK user) and the Anthropic API.
"""

import json
import uuid
import time
from datetime import datetime
from collections import deque

SCHEMA_VERSION = "1.0"
CONTEXT_WINDOW_MAX = 200000


# ─── Step Builder ──────────────────────────────────────────────────────

def build_step_entry(request_body: dict, response_body: dict, state: dict) -> dict:
    """
    Build a trajectory step entry from raw request/response dicts.
    Works with both proxy (raw JSON) and interceptor (SDK objects converted to dicts).

    Args:
        request_body: The original API request JSON (messages, model, tools, system, etc.)
        response_body: The reconstructed response dict (content, usage, stop_reason)
        state: Mutable session state dict (step_counter, cumulative tokens, etc.)
    """
    state["step_counter"] += 1

    input_tokens = response_body.get("usage", {}).get("input_tokens", 0)
    output_tokens = response_body.get("usage", {}).get("output_tokens", 0)
    state["cumulative_input_tokens"] += input_tokens
    state["cumulative_output_tokens"] += output_tokens

    # Extract tool calls and text from response content
    tool_calls = []
    text_content = ""
    for block in response_body.get("content", []):
        if block.get("type") == "tool_use":
            tool_calls.append({
                "name": block.get("name", ""),
                "input_summary": str(block.get("input", ""))[:200],
            })
            state["tool_call_history"].append(
                f"{block.get('name', '')}:{str(block.get('input', ''))[:100]}"
            )
        elif block.get("type") == "text":
            text_content = block.get("text", "")[:300]

    # Extract request metadata
    system_prompt_tokens = 0
    system = request_body.get("system", "")
    if isinstance(system, str):
        system_prompt_tokens = len(system) // 4
    elif isinstance(system, list):
        system_prompt_tokens = sum(len(str(s)) for s in system) // 4

    tools_provided = []
    for t in request_body.get("tools", []):
        tools_provided.append(t.get("name", ""))

    entry = {
        "schema_version": SCHEMA_VERSION,
        "session_id": state["session_id"],
        "step_id": state["step_counter"],
        "timestamp": datetime.utcnow().isoformat(),
        "request": {
            "message_count": len(request_body.get("messages", [])),
            "total_input_tokens": input_tokens,
            "tools_provided": tools_provided,
            "system_prompt_tokens": system_prompt_tokens,
        },
        "response": {
            "output_tokens": output_tokens,
            "stop_reason": response_body.get("stop_reason", ""),
            "tools_called": tool_calls,
            "text_summary": text_content,
        },
        "trajectory_metrics": {
            "context_utilization_pct": round(
                (state["cumulative_input_tokens"] / CONTEXT_WINDOW_MAX) * 100, 1
            ),
            "cumulative_tokens": state["cumulative_input_tokens"] + state["cumulative_output_tokens"],
            "context_window_max": CONTEXT_WINDOW_MAX,
            "step_duration_ms": state.get("last_step_duration_ms", 0),
            "files_touched": list(set(
                str(block.get("input", {}).get("path", ""))
                for block in response_body.get("content", [])
                if block.get("type") == "tool_use"
                and isinstance(block.get("input"), dict)
                and "path" in block.get("input", {})
            )),
            "unique_tools_this_session": len(set(
                tc.split(":")[0] for tc in state["tool_call_history"]
            )),
            "repeated_file_reads": sum(
                1 for tc in state["tool_call_history"]
                if tc.startswith("read_file:") or tc.startswith("Read:")
            ),
        },
        "model": request_body.get("model", "unknown"),
        "guardrail_injected": state.get("last_guardrail"),
    }

    # Clear the last guardrail after recording
    state["last_guardrail"] = None

    return entry


# ─── SSE Stream Accumulator ───────────────────────────────────────────

class SSEAccumulator:
    """Accumulates SSE events into a reconstructed response dict."""

    def __init__(self):
        self.response = {
            "id": "",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": "",
            "stop_reason": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        self._current_block_index = -1
        self._tool_input_jsons: dict[int, str] = {}  # index -> accumulated json string

    def process_event(self, event_type: str, data: dict):
        """Process a single SSE event and update the accumulated response."""
        if event_type == "message_start":
            msg = data.get("message", {})
            self.response["id"] = msg.get("id", "")
            self.response["model"] = msg.get("model", "")
            usage = msg.get("usage", {})
            self.response["usage"]["input_tokens"] = usage.get("input_tokens", 0)

        elif event_type == "content_block_start":
            block = data.get("content_block", {})
            index = data.get("index", 0)
            self._current_block_index = index

            if block.get("type") == "text":
                self.response["content"].append({"type": "text", "text": ""})
            elif block.get("type") == "tool_use":
                self.response["content"].append({
                    "type": "tool_use",
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": {},
                })
                self._tool_input_jsons[index] = ""

        elif event_type == "content_block_delta":
            delta = data.get("delta", {})
            index = data.get("index", self._current_block_index)

            if delta.get("type") == "text_delta":
                if index < len(self.response["content"]):
                    self.response["content"][index]["text"] += delta.get("text", "")

            elif delta.get("type") == "input_json_delta":
                if index in self._tool_input_jsons:
                    self._tool_input_jsons[index] += delta.get("partial_json", "")

        elif event_type == "content_block_stop":
            index = data.get("index", self._current_block_index)
            # Parse accumulated tool input JSON
            if index in self._tool_input_jsons:
                try:
                    parsed = json.loads(self._tool_input_jsons[index])
                    if index < len(self.response["content"]):
                        self.response["content"][index]["input"] = parsed
                except (json.JSONDecodeError, ValueError):
                    pass

        elif event_type == "message_delta":
            delta = data.get("delta", {})
            self.response["stop_reason"] = delta.get("stop_reason")
            usage = data.get("usage", {})
            self.response["usage"]["output_tokens"] = usage.get("output_tokens", 0)

        elif event_type == "message_stop":
            pass  # Stream complete

    def get_response(self) -> dict:
        """Return the fully reconstructed response dict."""
        return self.response


# ─── Guardrail Checker ─────────────────────────────────────────────────

def check_guardrails(steps: list[dict], state: dict) -> dict | None:
    """
    Check for failure patterns that warrant intervention.
    Returns a guardrail dict {type, message} or None.

    Checks in priority order:
    1. Error Spiral (highest)
    2. Loop Detection
    3. Context Rot (lowest)
    """
    if len(steps) < 3:
        return None

    # --- Error Spiral: 3+ consecutive steps with error + retry language ---
    consecutive_errors = 0
    for step in reversed(steps):
        summary = step.get("response", {}).get("text_summary", "").lower()
        stop = step.get("response", {}).get("stop_reason", "")
        error_kw = any(kw in summary for kw in ["error", "fail", "econnrefused", "cannot connect", "traceback"])
        retry_kw = any(kw in summary for kw in ["again", "retry", "still", "persists", "try once more", "another approach"])
        if stop == "error" or (error_kw and retry_kw):
            consecutive_errors += 1
        else:
            break

    if consecutive_errors >= 3:
        return {
            "type": "ERROR_SPIRAL",
            "message": (
                "[AgentLens Coach] You are in an error spiral — "
                f"{consecutive_errors} consecutive error-retry cycles detected. "
                "STOP retrying the same approach. Pause completely, analyze the root cause "
                "of the errors, and take a fundamentally different approach to solve this problem."
            ),
        }

    # --- Loop Detection: tool signature pattern repeats ---
    # Filter out Haiku summarization calls (no tools, tiny output) — they are
    # internal Claude Code bookkeeping and pollute loop detection
    real_steps = [
        s for s in steps
        if s.get("response", {}).get("tools_called")
        or s.get("response", {}).get("output_tokens", 0) > 100
    ]

    recent = real_steps[-9:] if len(real_steps) >= 9 else real_steps
    signatures = []
    for s in recent:
        tools = s.get("response", {}).get("tools_called", [])
        parts = []
        for tc in tools:
            name = tc.get("name", "")
            input_sum = tc.get("input_summary", "")
            # Extract a short target identifier from the input summary
            # Handle both quote styles: 'key': 'value' and "key": "value"
            target = ""
            for prefix in ["file_path': '", 'file_path": "', "path': '", 'path": "', "command': '", 'command": "']:
                idx = input_sum.find(prefix)
                if idx >= 0:
                    start = idx + len(prefix)
                    # Find the matching close quote
                    close_char = prefix[-1]  # ' or "
                    end = input_sum.find(close_char, start)
                    if end < 0:
                        end = min(start + 80, len(input_sum))
                    target = input_sum[start:end]
                    # For commands, just keep the first meaningful part (up to first newline or pipe)
                    if "command" in prefix:
                        for sep in ["\n", "\\n", " | ", " && ", " 2>&1"]:
                            cut = target.find(sep)
                            if cut > 0:
                                target = target[:cut]
                                break
                    break
            parts.append(f"{name}:{target}" if target else name)
        sig = "|".join(parts)
        if sig:  # skip empty signatures (shouldn't happen after filtering but safety check)
            signatures.append(sig)

    # Check for sequences of length 1-3 repeating 3+ times
    for seq_len in range(1, 4):
        if len(signatures) < seq_len * 3:
            continue
        for i in range(len(signatures) - seq_len * 3 + 1):
            pattern = signatures[i:i + seq_len]
            repeats = 0
            for j in range(3):
                chunk = signatures[i + j * seq_len:i + (j + 1) * seq_len]
                if chunk == pattern:
                    repeats += 1
                else:
                    break
            if repeats >= 3:
                display_names = [p.split(":")[0] for p in pattern]
                return {
                    "type": "LOOP",
                    "message": (
                        "[AgentLens Coach] Loop detected — you are repeating the same "
                        f"tool sequence ({' → '.join(display_names)}) on the same targets for {repeats} cycles. "
                        "Your current approach is not working. Step back, reassess your "
                        "understanding of the problem, and try a fundamentally different strategy."
                    ),
                }

    # --- Context Rot: utilization above 70% ---
    if steps:
        last_util = steps[-1].get("trajectory_metrics", {}).get("context_utilization_pct", 0)
        if last_util > 70:
            return {
                "type": "CONTEXT_ROT",
                "message": (
                    f"[AgentLens Coach] Your context window is {last_util:.0f}% full. "
                    "You are running low on working memory. Summarize what you have accomplished "
                    "so far, identify what remains, and focus on completing the most critical task."
                ),
            }

    return None


# ─── Session State Factory ─────────────────────────────────────────────

def new_session_state(session_id: str | None = None) -> dict:
    """Create a fresh session state dict."""
    return {
        "session_id": session_id or str(uuid.uuid4()),
        "step_counter": 0,
        "cumulative_input_tokens": 0,
        "cumulative_output_tokens": 0,
        "tool_call_history": [],
        "guardrails_triggered": [],
        "last_guardrail": None,
        "last_request_time": time.time(),
    }
