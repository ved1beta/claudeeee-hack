"""
AgentLens API Server — Transparent proxy, real-time analysis, session persistence.

Modes:
  1. Proxy: Set ANTHROPIC_BASE_URL=http://localhost:8000/proxy/v1 → all API calls flow through
  2. Ingest: InstrumentedClient pushes steps via POST /ingest
  3. Upload: Dashboard uploads .jsonl files via POST /analyze
"""

import json
import logging
import os
import re
import shutil
import tempfile
import time
import copy
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, UploadFile, File, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from analyzer import TrajectoryAnalyzer
from proxy import (
    build_step_entry,
    SSEAccumulator,
    check_guardrails,
    new_session_state,
    SCHEMA_VERSION,
)
from dotenv import load_dotenv

load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("agentlens")
logger.setLevel(logging.INFO)

_file_handler = logging.FileHandler(LOGS_DIR / "agentlens.log")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(_file_handler)

# Also log to stderr for uvicorn output
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_stream_handler)

app = FastAPI(title="AgentLens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── State ─────────────────────────────────────────────────────────────

# In-memory live sessions: session_id -> list of steps
sessions: dict[str, list[dict]] = {}
active_session_id: str | None = None

# Proxy session states: session_id -> state dict (step counter, cumulative tokens, etc.)
proxy_states: dict[str, dict] = {}

# Tag -> active session_id mapping (for parallel Claude Code instances)
tag_sessions: dict[str, str] = {}

# Pre-loaded branch sessions (from POST /branch)
branch_sessions: dict[str, dict] = {}

# Sessions directory for persistence
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

EMPTY_ANALYSIS = {
    "total_steps": 0, "health_score": 100, "session_id": None,
    "anomalies": {"loops": [], "context_decay": [], "repetition": [], "error_spirals": []},
    "steps": [],
    "summary": {"total_tokens": 0, "final_context_pct": 0, "total_tool_calls": 0, "total_duration_s": 0},
}

# Upstream Anthropic API
UPSTREAM_URL = "https://api.anthropic.com"
_http_client: httpx.AsyncClient | None = None

# Time gap (seconds) before a new session is created
SESSION_GAP_SECONDS = 300  # 5 minutes


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    return _http_client


def _slugify(text: str, max_len: int = 30) -> str:
    """Turn text into a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:max_len].strip('-') or "session"


def _make_session_id(messages: list[dict], tag: str | None = None) -> str:
    """Generate a human-readable session ID: YYYY-MM-DD_HH-MM_{tag-or-slug}_{uuid8}."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    uid = str(uuid.uuid4())[:8]

    if tag:
        # Use the tag directly as the slug
        task = _slugify(tag)
    else:
        # Extract task description from first user message
        task = "session"
        if messages:
            first_msg = messages[0]
            content = first_msg.get("content", "")
            if isinstance(content, str):
                task = _slugify(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        task = _slugify(block.get("text", ""))
                        break

    return f"{ts}_{task}_{uid}"


# ─── Helpers ───────────────────────────────────────────────────────────

def _analyze_steps(steps: list[dict]) -> dict:
    """Analyze a list of steps using a temp file."""
    if not steps:
        return dict(EMPTY_ANALYSIS)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        for step in steps:
            tmp.write(json.dumps(step) + "\n")
        tmp_path = tmp.name
    try:
        analyzer = TrajectoryAnalyzer(tmp_path)
        return analyzer.full_analysis()
    finally:
        os.unlink(tmp_path)


def _persist_step(session_id: str, step: dict):
    """Append a step to the session's JSONL file on disk."""
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(exist_ok=True)
    with open(session_dir / "steps.jsonl", "a") as f:
        f.write(json.dumps(step) + "\n")


def _save_checkpoint(session_id: str, step_id: int, messages: list[dict]):
    """Save full conversation state as a checkpoint."""
    session_dir = SESSIONS_DIR / session_id / "checkpoints"
    session_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "step_id": step_id,
        "timestamp": time.time(),
        "message_count": len(messages),
        "messages": messages,
    }
    with open(session_dir / f"step_{step_id}.json", "w") as f:
        json.dump(checkpoint, f)


def _ingest_step(session_id: str, step: dict):
    """Add step to in-memory session and persist to disk."""
    global active_session_id
    if session_id not in sessions:
        sessions[session_id] = []
    sessions[session_id].append(step)
    active_session_id = session_id
    _persist_step(session_id, step)


# ─── Root ──────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name": "AgentLens API",
        "version": "2.0",
        "proxy": "Set ANTHROPIC_BASE_URL=http://localhost:8000/proxy",
        "endpoints": [
            "/proxy/v1/messages", "/latest", "/sessions", "/history",
            "/checkpoints/{session_id}", "/branch", "/fix-report/{session_id}",
            "/logs",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════
# PROXY — Transparent interception of Anthropic API calls
# ═══════════════════════════════════════════════════════════════════════

@app.post("/proxy/v1/t/{tag}/messages")
@app.post("/proxy/v1/t/{tag}/v1/messages")
async def proxy_messages_tagged(tag: str, request: Request):
    """Tagged proxy — each tag gets its own independent session."""
    return await _proxy_messages_impl(request, tag=tag)


@app.post("/proxy/v1/messages")
@app.post("/proxy/v1/v1/messages")
@app.post("/v1/messages")
async def proxy_messages(request: Request):
    """Transparent proxy for Anthropic Messages API."""
    return await _proxy_messages_impl(request, tag=None)


async def _proxy_messages_impl(request: Request, tag: str | None = None):
    """
    Core proxy logic. Forwards requests to api.anthropic.com while logging trajectory data.
    If tag is provided, session is scoped to that tag (supports parallel Claude Code instances).
    """
    global active_session_id

    raw_body = await request.body()
    request_body = json.loads(raw_body)

    # --- Session detection (time-based, tag-scoped) ---
    messages = request_body.get("messages", [])

    # Check for explicit branch session header
    branch_id = request.headers.get("x-agentlens-session")

    # Determine which active session to check based on tag
    current_active = tag_sessions.get(tag) if tag else active_session_id

    if branch_id and branch_id in branch_sessions:
        # Resume from a branch
        sid = branch_id
        if sid not in proxy_states:
            proxy_states[sid] = branch_sessions.pop(branch_id)
    elif current_active and current_active in proxy_states:
        # Check time gap — if last request was recent, continue the session
        last_req_time = proxy_states[current_active].get("last_request_time", 0)
        gap = time.time() - last_req_time
        if gap < SESSION_GAP_SECONDS:
            sid = current_active
        else:
            # Gap too large — new session
            sid = _make_session_id(messages, tag=tag)
            proxy_states[sid] = new_session_state(sid)
            logger.info(f"NEW SESSION (gap={gap:.0f}s, tag={tag}): {sid}")
    else:
        # No active session — create one
        sid = _make_session_id(messages, tag=tag)
        proxy_states[sid] = new_session_state(sid)
        logger.info(f"NEW SESSION (tag={tag}): {sid}")

    # Update tag/global tracking
    if tag:
        tag_sessions[tag] = sid
    active_session_id = sid

    state = proxy_states[sid]
    state["last_request_time"] = time.time()
    state["last_message_count"] = len(messages)
    active_session_id = sid

    # --- Guardrails check ---
    # Skip guardrails entirely for sessions tagged with "noguard-" prefix
    # This enables unprotected A/B comparison runs through the proxy.
    skip_guardrails = tag and tag.startswith("noguard-")

    # Only run guardrails on real agent calls, not Haiku summarization requests.
    # Haiku summarization calls have very few messages and no tools provided.
    model = request_body.get("model", "")
    tools_provided = request_body.get("tools", [])
    is_summarization = "haiku" in model and len(tools_provided) == 0

    steps = sessions.get(sid, [])
    guardrail = None
    if not is_summarization and not skip_guardrails:
        # Cooldown: don't fire guardrail again within 60 seconds of last one
        last_guard_time = state.get("last_guardrail_time", 0)
        if time.time() - last_guard_time > 60:
            guardrail = check_guardrails(steps, state)

    forward_body = request_body
    if guardrail:
        forward_body = copy.deepcopy(request_body)
        state["last_guardrail"] = guardrail["type"]
        state["last_guardrail_time"] = time.time()
        logger.warning(f"GUARDRAIL {guardrail['type']} | {sid} | step {state['step_counter'] + 1}")
        state["guardrails_triggered"].append({
            "step": state["step_counter"] + 1,
            "type": guardrail["type"],
            "timestamp": time.time(),
        })
        # Inject into system prompt
        existing_system = forward_body.get("system", "")
        if isinstance(existing_system, str):
            forward_body["system"] = guardrail["message"] + "\n\n" + existing_system
        elif isinstance(existing_system, list):
            forward_body["system"] = [{"type": "text", "text": guardrail["message"]}] + existing_system
        else:
            forward_body["system"] = guardrail["message"]

    # --- Save checkpoint ---
    _save_checkpoint(sid, state["step_counter"] + 1, messages)

    # --- Forward headers ---
    forward_headers = {}
    for key in ["x-api-key", "anthropic-version", "anthropic-beta", "authorization"]:
        val = request.headers.get(key)
        if val:
            forward_headers[key] = val
    forward_headers["content-type"] = "application/json"

    # Fallback to .env API key if no auth header provided
    if "x-api-key" not in forward_headers and "authorization" not in forward_headers:
        env_key = os.getenv("ANTHROPIC_API_KEY")
        if env_key:
            forward_headers["x-api-key"] = env_key

    client = await get_http_client()
    start_time = time.time()

    is_streaming = forward_body.get("stream", False)

    if is_streaming:
        # --- Streaming proxy ---
        upstream_req = client.build_request(
            "POST",
            f"{UPSTREAM_URL}/v1/messages",
            headers=forward_headers,
            content=json.dumps(forward_body),
        )
        upstream_resp = await client.send(upstream_req, stream=True)

        # Check for upstream errors (auth failures, etc.)
        if upstream_resp.status_code != 200:
            error_body = await upstream_resp.aread()
            await upstream_resp.aclose()
            from fastapi.responses import Response
            return Response(
                content=error_body,
                status_code=upstream_resp.status_code,
                media_type="application/json",
            )

        accumulator = SSEAccumulator()

        async def stream_and_accumulate():
            try:
                async for line in upstream_resp.aiter_lines():
                    yield line + "\n"

                    # Parse SSE events
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                            event_type = data.get("type", "")
                            accumulator.process_event(event_type, data)
                        except json.JSONDecodeError:
                            pass
                    elif line.startswith("event: "):
                        pass  # event type line, we get type from data

            finally:
                await upstream_resp.aclose()

                # Build step entry from accumulated response
                duration_ms = (time.time() - start_time) * 1000
                state["last_step_duration_ms"] = round(duration_ms)
                response_body = accumulator.get_response()
                step_entry = build_step_entry(request_body, response_body, state)
                _ingest_step(sid, step_entry)

                tools = [t["name"] for t in step_entry.get("response", {}).get("tools_called", [])]
                logger.info(
                    f"STEP {step_entry['step_id']} | {sid} | "
                    f"model={step_entry.get('model','?')} | "
                    f"tools={tools} | "
                    f"in={response_body.get('usage',{}).get('input_tokens',0)} "
                    f"out={response_body.get('usage',{}).get('output_tokens',0)} | "
                    f"{round(duration_ms)}ms"
                )

        return StreamingResponse(
            stream_and_accumulate(),
            media_type="text/event-stream",
            headers={
                "cache-control": "no-cache",
                "x-agentlens-session": sid,
            },
        )

    else:
        # --- Non-streaming proxy ---
        resp = await client.post(
            f"{UPSTREAM_URL}/v1/messages",
            headers=forward_headers,
            content=json.dumps(forward_body),
        )
        duration_ms = (time.time() - start_time) * 1000
        state["last_step_duration_ms"] = round(duration_ms)

        response_body = resp.json()

        # If upstream returned an error, pass it through without logging as step
        if resp.status_code != 200:
            from fastapi.responses import JSONResponse
            return JSONResponse(content=response_body, status_code=resp.status_code)

        step_entry = build_step_entry(request_body, response_body, state)
        _ingest_step(sid, step_entry)

        tools = [t["name"] for t in step_entry.get("response", {}).get("tools_called", [])]
        logger.info(
            f"STEP {step_entry['step_id']} | {sid} | "
            f"model={step_entry.get('model','?')} | "
            f"tools={tools} | "
            f"in={response_body.get('usage',{}).get('input_tokens',0)} "
            f"out={response_body.get('usage',{}).get('output_tokens',0)} | "
            f"{round(duration_ms)}ms"
        )

        return response_body


# Passthrough for model listing (Claude Code may call this)
@app.get("/proxy/v1/t/{tag}/models")
@app.get("/proxy/v1/models")
@app.get("/proxy/v1/v1/models")
@app.get("/v1/models")
async def proxy_models(request: Request, tag: str | None = None):
    client = await get_http_client()
    headers = {}
    for key in ["x-api-key", "anthropic-version", "authorization"]:
        val = request.headers.get(key)
        if val:
            headers[key] = val
    if "x-api-key" not in headers and "authorization" not in headers:
        env_key = os.getenv("ANTHROPIC_API_KEY")
        if env_key:
            headers["x-api-key"] = env_key
    resp = await client.get(f"{UPSTREAM_URL}/v1/models", headers=headers)
    return resp.json()


# Catch-all for other proxy paths (including tagged)
@app.api_route("/proxy/v1/t/{tag}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/proxy/v1/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/proxy/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_catchall(path: str, request: Request, tag: str | None = None):
    client = await get_http_client()
    headers = {}
    for key in ["x-api-key", "anthropic-version", "anthropic-beta", "authorization", "content-type"]:
        val = request.headers.get(key)
        if val:
            headers[key] = val
    if "x-api-key" not in headers and "authorization" not in headers:
        env_key = os.getenv("ANTHROPIC_API_KEY")
        if env_key:
            headers["x-api-key"] = env_key
    body = await request.body()
    # Strip any extra /v1 prefix from path (Claude Code sends /v1/v1/...)
    clean_path = path.lstrip("/")
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]
    resp = await client.request(
        request.method,
        f"{UPSTREAM_URL}/v1/{clean_path}",
        headers=headers,
        content=body if body else None,
    )
    from fastapi.responses import Response
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


# ═══════════════════════════════════════════════════════════════════════
# LIVE SESSION ENDPOINTS (interceptor + dashboard)
# ═══════════════════════════════════════════════════════════════════════

@app.post("/ingest")
async def ingest(request: Request):
    """Receive a single step from the interceptor in real-time."""
    step = await request.json()
    sid = step.get("session_id", "default")
    _ingest_step(sid, step)
    return {"ok": True, "session_id": sid, "total_steps": len(sessions.get(sid, []))}


@app.get("/sessions")
def list_sessions():
    """List all live sessions."""
    result = []
    for sid, steps in sessions.items():
        result.append({
            "session_id": sid,
            "total_steps": len(steps),
            "active": sid == active_session_id,
            "started_at": steps[0].get("timestamp") if steps else None,
        })
    return {"sessions": result}


@app.get("/latest")
def get_latest(session_id: str | None = None):
    """Return analysis of a live session."""
    sid = session_id or active_session_id
    if sid and sid in sessions and sessions[sid]:
        analysis = _analyze_steps(sessions[sid])
        analysis["session_id"] = sid
        # Include guardrail info
        if sid in proxy_states:
            analysis["guardrails_triggered"] = proxy_states[sid].get("guardrails_triggered", [])
        return analysis

    if os.path.exists("analysis.json"):
        with open("analysis.json") as f:
            return json.load(f)
    return dict(EMPTY_ANALYSIS)


@app.delete("/session")
def clear_session(session_id: str | None = None):
    """Clear a live session (or all)."""
    global active_session_id
    if session_id:
        sessions.pop(session_id, None)
        proxy_states.pop(session_id, None)
        if active_session_id == session_id:
            active_session_id = None
        return {"ok": True, "message": f"Session {session_id} cleared"}
    sessions.clear()
    proxy_states.clear()
    active_session_id = None
    return {"ok": True, "message": "All sessions cleared"}


# ═══════════════════════════════════════════════════════════════════════
# HISTORY — Past session persistence
# ═══════════════════════════════════════════════════════════════════════

@app.get("/history")
def list_history():
    """List all persisted past sessions."""
    result = []
    if not SESSIONS_DIR.exists():
        return {"sessions": []}

    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        if not session_dir.is_dir():
            continue
        steps_file = session_dir / "steps.jsonl"
        if not steps_file.exists():
            continue

        # Read first and last step for metadata
        lines = steps_file.read_text().strip().split("\n")
        total = len(lines)
        if total == 0:
            continue

        first = json.loads(lines[0])
        has_checkpoints = (session_dir / "checkpoints").exists()

        # Parse readable name from session ID format: YYYY-MM-DD_HH-MM_slug_uuid8
        sid = session_dir.name
        parts = sid.split("_", 3)
        if len(parts) >= 3:
            display_name = " ".join(parts[2:-1]) if len(parts) > 3 else parts[2]
            display_name = display_name.replace("-", " ").title()
        else:
            display_name = sid[:20]

        result.append({
            "session_id": sid,
            "display_name": display_name,
            "started_at": first.get("timestamp"),
            "total_steps": total,
            "has_checkpoints": has_checkpoints,
        })

    return {"sessions": result}


@app.get("/history/{session_id}")
def get_history_session(session_id: str):
    """Load and analyze a past session."""
    steps_file = SESSIONS_DIR / session_id / "steps.jsonl"
    if not steps_file.exists():
        return {"error": "Session not found"}

    steps = []
    for line in steps_file.read_text().strip().split("\n"):
        if line:
            steps.append(json.loads(line))

    analysis = _analyze_steps(steps)
    analysis["session_id"] = session_id
    return analysis


@app.delete("/history/{session_id}")
def delete_history_session(session_id: str):
    """Delete a persisted session."""
    session_dir = SESSIONS_DIR / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
        return {"ok": True, "message": f"Session {session_id} deleted"}
    return {"error": "Session not found"}


# ═══════════════════════════════════════════════════════════════════════
# LOGS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/logs")
def get_logs(
    lines: int = Query(100, ge=1, le=2000),
    session_id: str | None = None,
):
    """Return recent log lines, optionally filtered by session_id."""
    log_file = LOGS_DIR / "agentlens.log"
    if not log_file.exists():
        return {"lines": [], "total": 0}

    all_lines = log_file.read_text().strip().split("\n")

    if session_id:
        all_lines = [l for l in all_lines if session_id in l]

    recent = all_lines[-lines:]
    return {"lines": recent, "total": len(all_lines), "showing": len(recent)}


# ═══════════════════════════════════════════════════════════════════════
# CHECKPOINTS + BRANCH (Time Travel)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/checkpoints/{session_id}")
def list_checkpoints(session_id: str):
    """List all checkpoints for a session."""
    cp_dir = SESSIONS_DIR / session_id / "checkpoints"
    if not cp_dir.exists():
        return {"session_id": session_id, "checkpoints": []}

    checkpoints = []
    for cp_file in sorted(cp_dir.glob("step_*.json")):
        with open(cp_file) as f:
            cp = json.load(f)
        checkpoints.append({
            "step_id": cp["step_id"],
            "timestamp": cp.get("timestamp"),
            "message_count": cp.get("message_count", 0),
        })

    return {"session_id": session_id, "checkpoints": checkpoints}


@app.post("/branch")
async def create_branch(request: Request):
    """
    Create a new session branching from a checkpoint.
    Uses Claude meta-analysis to generate a corrective prompt.
    """
    body = await request.json()
    session_id = body["session_id"]
    from_step = body["from_step"]

    # Load checkpoint
    cp_file = SESSIONS_DIR / session_id / "checkpoints" / f"step_{from_step}.json"
    if not cp_file.exists():
        return {"error": f"Checkpoint at step {from_step} not found"}

    with open(cp_file) as f:
        checkpoint = json.load(f)

    # Load all steps and analyze what went wrong after the checkpoint
    steps_file = SESSIONS_DIR / session_id / "steps.jsonl"
    all_steps = []
    for line in steps_file.read_text().strip().split("\n"):
        if line:
            all_steps.append(json.loads(line))

    steps_after = [s for s in all_steps if s["step_id"] > from_step]

    if steps_after:
        analysis = _analyze_steps(steps_after)
        # Generate corrective prompt
        from meta_analyzer import generate_corrective_prompt
        corrective_prompt = generate_corrective_prompt(analysis, from_step)
    else:
        corrective_prompt = "No steps after checkpoint to analyze."

    # Create new branch session
    new_sid = f"branch-{str(uuid.uuid4())[:8]}-from-{from_step}"
    branch_state = new_session_state(new_sid)

    # Pre-load the branch for the proxy to pick up
    branch_sessions[new_sid] = branch_state

    return {
        "new_session_id": new_sid,
        "parent_session_id": session_id,
        "branched_from_step": from_step,
        "corrective_prompt": corrective_prompt,
        "checkpoint_messages": len(checkpoint.get("messages", [])),
        "instructions": f"Run: ANTHROPIC_BASE_URL=http://localhost:8000/proxy/v1 your-agent-command",
    }


# ═══════════════════════════════════════════════════════════════════════
# FIX REPORT
# ═══════════════════════════════════════════════════════════════════════

@app.post("/fix-report/{session_id}")
def generate_fix_report(session_id: str):
    """Generate a comprehensive fix report for a session."""
    # Try live session first, then disk
    steps = sessions.get(session_id, [])
    if not steps:
        steps_file = SESSIONS_DIR / session_id / "steps.jsonl"
        if steps_file.exists():
            steps = [json.loads(l) for l in steps_file.read_text().strip().split("\n") if l]

    if not steps:
        return {"error": "Session not found"}

    analysis = _analyze_steps(steps)

    from meta_analyzer import analyze_trajectory_with_claude
    try:
        meta_result = json.loads(analyze_trajectory_with_claude(analysis))
    except Exception:
        meta_result = {"error": "Meta-analysis failed"}

    return {
        "session_id": session_id,
        "analysis": analysis,
        "fix_report": meta_result,
    }


# ═══════════════════════════════════════════════════════════════════════
# FILE UPLOAD ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/sample")
def get_sample():
    if os.path.exists("analysis.json"):
        with open("analysis.json") as f:
            return json.load(f)
    return {"error": "No sample data."}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    content = await file.read()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        tmp.write(content.decode())
        tmp_path = tmp.name
    try:
        analyzer = TrajectoryAnalyzer(tmp_path)
        return analyzer.full_analysis()
    finally:
        os.unlink(tmp_path)


@app.post("/meta-analyze")
async def meta_analyze(file: UploadFile = File(...)):
    content = await file.read()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        tmp.write(content.decode())
        tmp_path = tmp.name
    try:
        analyzer = TrajectoryAnalyzer(tmp_path)
        analysis = analyzer.full_analysis()
        from meta_analyzer import analyze_trajectory_with_claude
        result = analyze_trajectory_with_claude(analysis)
        return {"analysis": analysis, "meta": json.loads(result)}
    finally:
        os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════
# A/B COMPARISON — Run two agent loops from the dashboard
# ═══════════════════════════════════════════════════════════════════════

from comparison_runner import run_comparison, get_comparison_status, comparisons as _comparisons


@app.post("/run-comparison")
async def start_comparison(request: Request):
    """Start an A/B comparison: unprotected vs protected agent run."""
    body = await request.json()
    prompt = body.get("prompt", "")
    repo_url = body.get("repo_url")

    if not prompt.strip():
        return {"error": "Prompt is required"}

    comp_id = await run_comparison(prompt, repo_url=repo_url)
    logger.info(f"COMPARISON STARTED | {comp_id} | prompt={prompt[:60]}")
    return {"comparison_id": comp_id, "status": "running"}


@app.get("/comparison/{comp_id}")
def get_comparison(comp_id: str):
    """Poll comparison status and results."""
    status = get_comparison_status(comp_id)
    if not status:
        return {"error": "Comparison not found"}

    result = {
        "comparison_id": comp_id,
        "status": status["status"],
        "prompt": status.get("prompt", ""),
        "unprotected": {
            "status": status["unprotected"]["status"],
            "steps": status["unprotected"]["steps"],
            "health": status["unprotected"]["health"],
        },
        "protected": {
            "status": status["protected"]["status"],
            "steps": status["protected"]["steps"],
            "health": status["protected"]["health"],
        },
    }

    # Include full data when completed
    if status["status"] == "completed":
        if status["unprotected"].get("data"):
            result["unprotected_data"] = status["unprotected"]["data"]
        if status["protected"].get("data"):
            result["protected_data"] = status["protected"]["data"]

    return result


# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
