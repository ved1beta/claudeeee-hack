import anthropic
import json
import time
import threading
import urllib.request
import uuid
from datetime import datetime

SCHEMA_VERSION = "1.0"


def _push_to_server(entry: dict, server_url: str):
    """Fire-and-forget POST to the AgentLens server."""
    try:
        data = json.dumps(entry).encode()
        req = urllib.request.Request(
            f"{server_url}/ingest",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # Server might not be running, that's fine


class InstrumentedMessages:
    def __init__(self, client, log_file, state, server_url):
        self._client = client
        self._log_file = log_file
        self._state = state
        self._server_url = server_url

    def create(self, **kwargs):
        self._state["step_counter"] += 1
        start_time = time.time()

        response = self._client.messages.create(**kwargs)

        duration_ms = (time.time() - start_time) * 1000

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        self._state["cumulative_input_tokens"] += input_tokens
        self._state["cumulative_output_tokens"] += output_tokens

        tool_calls = []
        text_content = ""
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "name": block.name,
                    "input_summary": str(block.input)[:200],
                })
                self._state["tool_call_history"].append(
                    f"{block.name}:{str(block.input)[:100]}"
                )
            elif block.type == "text":
                text_content = block.text[:300]

        system_prompt_tokens = 0
        if "system" in kwargs:
            system_prompt_tokens = len(str(kwargs["system"])) // 4

        tools_provided = []
        if "tools" in kwargs:
            tools_provided = [t.get("name", "") for t in kwargs["tools"]]

        context_window_max = 200000
        entry = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self._state["session_id"],
            "step_id": self._state["step_counter"],
            "timestamp": datetime.utcnow().isoformat(),
            "request": {
                "message_count": len(kwargs.get("messages", [])),
                "total_input_tokens": input_tokens,
                "tools_provided": tools_provided,
                "system_prompt_tokens": system_prompt_tokens,
            },
            "response": {
                "output_tokens": output_tokens,
                "stop_reason": response.stop_reason,
                "tools_called": tool_calls,
                "text_summary": text_content,
            },
            "trajectory_metrics": {
                "context_utilization_pct": round(
                    (self._state["cumulative_input_tokens"] / context_window_max) * 100, 1
                ),
                "cumulative_tokens": self._state["cumulative_input_tokens"] + self._state["cumulative_output_tokens"],
                "context_window_max": context_window_max,
                "step_duration_ms": round(duration_ms),
                "files_touched": list(set(
                    str(block.input.get("path", ""))
                    for block in response.content
                    if block.type == "tool_use" and isinstance(block.input, dict) and "path" in block.input
                )),
                "unique_tools_this_session": len(set(
                    tc.split(":")[0] for tc in self._state["tool_call_history"]
                )),
                "repeated_file_reads": sum(
                    1 for tc in self._state["tool_call_history"]
                    if tc.startswith("read_file:")
                ),
            },
            "model": kwargs.get("model", "unknown"),
        }

        # Write to log file
        self._log_file.write(json.dumps(entry) + "\n")
        self._log_file.flush()

        # Push to server in background (non-blocking)
        if self._server_url:
            threading.Thread(
                target=_push_to_server,
                args=(entry, self._server_url),
                daemon=True,
            ).start()

        return response


class InstrumentedClient:
    """
    Drop-in replacement for anthropic.Anthropic().

    Usage:
        # Instead of: client = anthropic.Anthropic(api_key="sk-...")
        client = InstrumentedClient(api_key="sk-...")

        # Use exactly the same way:
        response = client.messages.create(model="...", messages=[...])

        # trajectory.jsonl is written automatically
        # If AgentLens server is running, data streams to dashboard live

    Args:
        trajectory_log: Path to JSONL log file (default: "trajectory.jsonl")
        server_url: AgentLens server URL (default: "http://localhost:8000")
                    Set to None to disable live streaming
        **kwargs: Passed directly to anthropic.Anthropic()
    """
    def __init__(self, **kwargs):
        log_path = kwargs.pop("trajectory_log", "trajectory.jsonl")
        server_url = kwargs.pop("server_url", "http://localhost:8000")
        self._client = anthropic.Anthropic(**kwargs)
        self._log_file = open(log_path, "a")
        self._state = {
            "session_id": str(uuid.uuid4()),
            "step_counter": 0,
            "cumulative_input_tokens": 0,
            "cumulative_output_tokens": 0,
            "tool_call_history": [],
        }
        self.messages = InstrumentedMessages(self._client, self._log_file, self._state, server_url)

    def close(self):
        self._log_file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
