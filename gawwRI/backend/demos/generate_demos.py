"""
Generate two realistic demo trajectories for AgentLens:
  1. unprotected.jsonl — agent spirals, loops, crashes (health → 12)
  2. protected.jsonl   — same task, AgentLens guardrails fire, agent recovers (health → 78)

Task: "Refactor this Flask app to use async with quart, add error handling, write tests"
"""

import json
import uuid
from datetime import datetime, timedelta

SCHEMA = "1.0"
SID_BAD = "demo-unprotected"
SID_GOOD = "demo-protected"
CTX_MAX = 200000

def step(sid, step_id, ts, input_tok, output_tok, cum_in, cum_out,
         tools_called, text_summary, stop_reason="end_turn",
         tools_provided=None, system_tokens=800, model="claude-sonnet-4-20250514",
         duration_ms=3000, guardrail=None, files=None):
    return {
        "schema_version": SCHEMA,
        "session_id": sid,
        "step_id": step_id,
        "timestamp": ts.isoformat(),
        "request": {
            "message_count": step_id * 2 + 1,
            "total_input_tokens": input_tok,
            "tools_provided": tools_provided or ["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            "system_prompt_tokens": system_tokens,
        },
        "response": {
            "output_tokens": output_tok,
            "stop_reason": stop_reason,
            "tools_called": tools_called,
            "text_summary": text_summary,
        },
        "trajectory_metrics": {
            "context_utilization_pct": round((cum_in / CTX_MAX) * 100, 1),
            "cumulative_tokens": cum_in + cum_out,
            "context_window_max": CTX_MAX,
            "step_duration_ms": duration_ms,
            "files_touched": files or [],
            "unique_tools_this_session": 6,
            "repeated_file_reads": 0,
        },
        "model": model,
        "guardrail_injected": guardrail,
    }

def tc(name, input_summary):
    return {"name": name, "input_summary": input_summary}


# ═══════════════════════════════════════════════════════════════════════
# UNPROTECTED — Agent spirals and dies
# ═══════════════════════════════════════════════════════════════════════

def generate_unprotected():
    steps = []
    t = datetime(2026, 2, 15, 10, 0, 0)
    cum_in = 0
    cum_out = 0

    # Phase 1: Good start (steps 1-6) — exploring the codebase
    s = 1; cum_in += 3200; cum_out += 450
    steps.append(step(SID_BAD, s, t, 3200, 450, cum_in, cum_out,
        [tc("Glob", "pattern='**/*.py'"), tc("Read", "file_path': '/app/app.py'")],
        "Let me explore the Flask app structure first.",
        stop_reason="tool_use", duration_ms=2800,
        files=["/app/app.py"]))

    t += timedelta(seconds=5); s = 2; cum_in += 8500; cum_out += 600
    steps.append(step(SID_BAD, s, t, 8500, 600, cum_in, cum_out,
        [tc("Read", "file_path': '/app/models.py'"), tc("Read", "file_path': '/app/routes.py'")],
        "Reading the models and routes to understand the app structure.",
        stop_reason="tool_use", duration_ms=3200,
        files=["/app/models.py", "/app/routes.py"]))

    t += timedelta(seconds=6); s = 3; cum_in += 12000; cum_out += 800
    steps.append(step(SID_BAD, s, t, 12000, 800, cum_in, cum_out,
        [tc("Read", "file_path': '/app/database.py'"), tc("Read", "file_path': '/app/config.py'")],
        "Understanding the database layer and configuration.",
        stop_reason="tool_use", duration_ms=4100,
        files=["/app/database.py", "/app/config.py"]))

    t += timedelta(seconds=8); s = 4; cum_in += 15000; cum_out += 1200
    steps.append(step(SID_BAD, s, t, 15000, 1200, cum_in, cum_out,
        [tc("Write", "file_path': '/app/app_async.py'")],
        "Creating the async version of the main app using Quart.",
        stop_reason="tool_use", duration_ms=8500,
        files=["/app/app_async.py"]))

    t += timedelta(seconds=12); s = 5; cum_in += 18000; cum_out += 900
    steps.append(step(SID_BAD, s, t, 18000, 900, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'def get_users'")],
        "Converting routes to async - starting with get_users endpoint.",
        stop_reason="tool_use", duration_ms=5200,
        files=["/app/routes.py"]))

    t += timedelta(seconds=8); s = 6; cum_in += 22000; cum_out += 1100
    steps.append(step(SID_BAD, s, t, 22000, 1100, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'def create_user'")],
        "Converting create_user endpoint to async.",
        stop_reason="tool_use", duration_ms=6100,
        files=["/app/routes.py"]))

    # Phase 2: First test run fails (steps 7-9)
    t += timedelta(seconds=10); s = 7; cum_in += 26000; cum_out += 500
    steps.append(step(SID_BAD, s, t, 26000, 500, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v'")],
        "Running tests to check the async conversion.",
        stop_reason="tool_use", duration_ms=12000,
        files=[]))

    t += timedelta(seconds=15); s = 8; cum_in += 32000; cum_out += 800
    steps.append(step(SID_BAD, s, t, 32000, 800, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'from flask import'")],
        "Tests failed with import error. Fixing the imports to use quart instead of flask.",
        stop_reason="tool_use", duration_ms=4500,
        files=["/app/routes.py"]))

    t += timedelta(seconds=8); s = 9; cum_in += 36000; cum_out += 500
    steps.append(step(SID_BAD, s, t, 36000, 500, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v'")],
        "Running tests again after import fix.",
        stop_reason="tool_use", duration_ms=11000,
        files=[]))

    # Phase 3: LOOP BEGINS — Edit→Test→Edit→Test cycle (steps 10-21)
    for i in range(6):
        base_s = 10 + i * 2
        cum_in += 8000 + i * 3000
        cum_out += 600

        t += timedelta(seconds=10)
        steps.append(step(SID_BAD, base_s, t, 8000 + i*3000, 600, cum_in, cum_out,
            [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def get_users'")],
            f"Tests still failing. Error: 'coroutine object has no attribute json'. Trying to fix the async handler again. Attempt {i+1}.",
            stop_reason="tool_use", duration_ms=5000 + i*800,
            files=["/app/routes.py"]))

        cum_in += 6000 + i * 2000
        cum_out += 400

        t += timedelta(seconds=12)
        steps.append(step(SID_BAD, base_s + 1, t, 6000 + i*2000, 400, cum_in, cum_out,
            [tc("Bash", "command': 'cd /app && python -m pytest tests/test_routes.py -v'")],
            f"Running tests again. Still getting 'coroutine' error. The await is not being applied correctly. Will retry with different approach.",
            stop_reason="tool_use", duration_ms=11000 + i*500,
            files=[]))

    # Phase 4: ERROR SPIRAL — things get worse (steps 22-28)
    for i in range(7):
        s = 22 + i
        cum_in += 12000 + i * 4000
        cum_out += 500

        t += timedelta(seconds=15)
        error_msgs = [
            "Error: ModuleNotFoundError 'quart'. Trying to install it. pip install quart failed with permission error. Retrying with --user flag.",
            "Still getting ModuleNotFoundError. The virtual environment seems broken. Trying to recreate it. Error persists after retry.",
            "Cannot connect to database after async conversion. Error: 'connection pool exhausted'. Trying again with different pool config.",
            "Error: ECONNREFUSED on database connection. The async driver is not compatible. Trying another approach with aiosqlite. Still failing.",
            "Traceback: TypeError in async context manager. The database session is not async-compatible. Error persists after multiple retries.",
            "Error cascade: test runner crashes with 'RuntimeError: no running event loop'. Tried again with asyncio.run() wrapper. Still failing.",
            "Fatal: all 23 tests failing. Import errors, connection errors, async errors compounding. Trying to revert to sync and start over.",
        ]

        steps.append(step(SID_BAD, s, t, 12000 + i*4000, 500, cum_in, cum_out,
            [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v'"),
             tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def'")],
            error_msgs[i],
            stop_reason="tool_use", duration_ms=15000 + i*2000,
            files=["/app/routes.py"]))

    # Phase 5: Context exhaustion (steps 29-32)
    for i in range(4):
        s = 29 + i
        cum_in += 20000
        cum_out += 300

        t += timedelta(seconds=20)
        steps.append(step(SID_BAD, s, t, 20000, 300, cum_in, cum_out,
            [tc("Read", "file_path': '/app/routes.py'"),
             tc("Read", "file_path': '/app/app.py'")],
            "Re-reading the entire codebase trying to understand what went wrong. Context window filling up rapidly. Lost track of what was already tried.",
            stop_reason="tool_use", duration_ms=8000,
            files=["/app/routes.py", "/app/app.py"]))

    return steps


# ═══════════════════════════════════════════════════════════════════════
# PROTECTED — Same task, AgentLens saves the session
# ═══════════════════════════════════════════════════════════════════════

def generate_protected():
    steps = []
    t = datetime(2026, 2, 15, 10, 0, 0)
    cum_in = 0
    cum_out = 0

    # Phase 1: Same good start (steps 1-6) — lower token counts
    s = 1; cum_in += 2400; cum_out += 350
    steps.append(step(SID_GOOD, s, t, 2400, 350, cum_in, cum_out,
        [tc("Glob", "pattern='**/*.py'"), tc("Read", "file_path': '/app/app.py'")],
        "Let me explore the Flask app structure first.",
        stop_reason="tool_use", duration_ms=2800,
        files=["/app/app.py"]))

    t += timedelta(seconds=5); s = 2; cum_in += 4200; cum_out += 400
    steps.append(step(SID_GOOD, s, t, 4200, 400, cum_in, cum_out,
        [tc("Read", "file_path': '/app/models.py'"), tc("Read", "file_path': '/app/routes.py'")],
        "Reading the models and routes to understand the app structure.",
        stop_reason="tool_use", duration_ms=3200,
        files=["/app/models.py", "/app/routes.py"]))

    t += timedelta(seconds=6); s = 3; cum_in += 6800; cum_out += 500
    steps.append(step(SID_GOOD, s, t, 6800, 500, cum_in, cum_out,
        [tc("Read", "file_path': '/app/database.py'"), tc("Read", "file_path': '/app/config.py'")],
        "Understanding the database layer and configuration.",
        stop_reason="tool_use", duration_ms=4100,
        files=["/app/database.py", "/app/config.py"]))

    t += timedelta(seconds=8); s = 4; cum_in += 8000; cum_out += 800
    steps.append(step(SID_GOOD, s, t, 8000, 800, cum_in, cum_out,
        [tc("Bash", "command': 'pip install quart aiosqlite'")],
        "Installing async dependencies first before making changes.",
        stop_reason="tool_use", duration_ms=8000))

    t += timedelta(seconds=10); s = 5; cum_in += 10000; cum_out += 1200
    steps.append(step(SID_GOOD, s, t, 10000, 1200, cum_in, cum_out,
        [tc("Write", "file_path': '/app/app_async.py'")],
        "Creating the async version of the main app using Quart with proper async context.",
        stop_reason="tool_use", duration_ms=9200,
        files=["/app/app_async.py"]))

    t += timedelta(seconds=12); s = 6; cum_in += 12000; cum_out += 700
    steps.append(step(SID_GOOD, s, t, 12000, 700, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'def get_users'"),
         tc("Edit", "file_path': '/app/routes.py', 'old_string': 'def create_user'")],
        "Converting routes to async with proper await patterns.",
        stop_reason="tool_use", duration_ms=6800,
        files=["/app/routes.py"]))

    # Phase 2: First test fails, brief loop (steps 7-10)
    t += timedelta(seconds=10); s = 7; cum_in += 14000; cum_out += 400
    steps.append(step(SID_GOOD, s, t, 14000, 400, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v'")],
        "Running tests to check the async conversion.",
        stop_reason="tool_use", duration_ms=12000))

    t += timedelta(seconds=12); s = 8; cum_in += 16000; cum_out += 500
    steps.append(step(SID_GOOD, s, t, 16000, 500, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def get_users'"),
         tc("Read", "file_path': '/app/routes.py'")],
        "Tests failed. Fixing the async handler — coroutine not being awaited.",
        stop_reason="tool_use", duration_ms=4500,
        files=["/app/routes.py"]))

    t += timedelta(seconds=8); s = 9; cum_in += 18000; cum_out += 400
    steps.append(step(SID_GOOD, s, t, 18000, 400, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/test_routes.py -v'")],
        "Running tests again. Still getting coroutine error.",
        stop_reason="tool_use", duration_ms=11000))

    t += timedelta(seconds=10); s = 10; cum_in += 20000; cum_out += 500
    steps.append(step(SID_GOOD, s, t, 20000, 500, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def get_users'"),
         tc("Bash", "command': 'cd /app && python -m pytest tests/test_routes.py -v'")],
        "Error persists. Trying the same fix again with slight variation. Still failing.",
        stop_reason="tool_use", duration_ms=8200,
        files=["/app/routes.py"]))

    # Step 11: GUARDRAIL FIRES — LOOP DETECTED
    t += timedelta(seconds=8); s = 11; cum_in += 22000; cum_out += 900
    steps.append(step(SID_GOOD, s, t, 22000, 900, cum_in, cum_out,
        [tc("Read", "file_path': '/app/database.py'"),
         tc("Grep", "pattern='async', path='/app/'")],
        "Taking a step back. The issue is not in routes.py — the database layer is synchronous. I need to convert the database module to async first, then the routes will work.",
        stop_reason="tool_use", duration_ms=6800,
        guardrail="LOOP",
        files=["/app/database.py"]))

    # Phase 3: Recovered — agent takes different approach (steps 12-16)
    t += timedelta(seconds=10); s = 12; cum_in += 25000; cum_out += 1500
    steps.append(step(SID_GOOD, s, t, 25000, 1500, cum_in, cum_out,
        [tc("Write", "file_path': '/app/database_async.py'")],
        "Creating async database module using aiosqlite. This is the root cause — routes can't be async if the DB calls are blocking.",
        stop_reason="tool_use", duration_ms=11000,
        files=["/app/database_async.py"]))

    t += timedelta(seconds=14); s = 13; cum_in += 27000; cum_out += 600
    steps.append(step(SID_GOOD, s, t, 27000, 600, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'from database import'")],
        "Updating routes to import from the new async database module.",
        stop_reason="tool_use", duration_ms=4200,
        files=["/app/routes.py"]))

    t += timedelta(seconds=8); s = 14; cum_in += 29000; cum_out += 400
    steps.append(step(SID_GOOD, s, t, 29000, 400, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v'")],
        "Running tests — 18/23 passing now! The async database fix resolved the core issue.",
        stop_reason="tool_use", duration_ms=12000))

    t += timedelta(seconds=15); s = 15; cum_in += 31000; cum_out += 800
    steps.append(step(SID_GOOD, s, t, 31000, 800, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def delete_user'"),
         tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def update_user'")],
        "Fixing the remaining 5 failing tests — delete_user and update_user need the same async DB pattern.",
        stop_reason="tool_use", duration_ms=7500,
        files=["/app/routes.py"]))

    t += timedelta(seconds=10); s = 16; cum_in += 33000; cum_out += 400
    steps.append(step(SID_GOOD, s, t, 33000, 400, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v'")],
        "All 23 tests passing! Async conversion is complete.",
        stop_reason="tool_use", duration_ms=11000))

    # Phase 4: Error handling + new tests (steps 17-22)
    t += timedelta(seconds=12); s = 17; cum_in += 35000; cum_out += 1200
    steps.append(step(SID_GOOD, s, t, 35000, 1200, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def get_users'"),
         tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def create_user'")],
        "Adding proper error handling — try/except with appropriate HTTP status codes for each endpoint.",
        stop_reason="tool_use", duration_ms=9800,
        files=["/app/routes.py"]))

    t += timedelta(seconds=12); s = 18; cum_in += 37000; cum_out += 1000
    steps.append(step(SID_GOOD, s, t, 37000, 1000, cum_in, cum_out,
        [tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def delete_user'"),
         tc("Edit", "file_path': '/app/routes.py', 'old_string': 'async def update_user'")],
        "Adding error handling to remaining endpoints. Using custom exception classes.",
        stop_reason="tool_use", duration_ms=8200,
        files=["/app/routes.py"]))

    t += timedelta(seconds=10); s = 19; cum_in += 39000; cum_out += 1800
    steps.append(step(SID_GOOD, s, t, 39000, 1800, cum_in, cum_out,
        [tc("Write", "file_path': '/app/tests/test_error_handling.py'")],
        "Writing comprehensive error handling tests — covering 400, 404, 500 responses.",
        stop_reason="tool_use", duration_ms=14000,
        files=["/app/tests/test_error_handling.py"]))

    t += timedelta(seconds=16); s = 20; cum_in += 41000; cum_out += 400
    steps.append(step(SID_GOOD, s, t, 41000, 400, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v --tb=short'")],
        "Running full test suite — 31/31 passing. All error handling tests pass.",
        stop_reason="tool_use", duration_ms=13000))

    t += timedelta(seconds=15); s = 21; cum_in += 43000; cum_out += 1500
    steps.append(step(SID_GOOD, s, t, 43000, 1500, cum_in, cum_out,
        [tc("Write", "file_path': '/app/tests/test_async_db.py'")],
        "Writing async database integration tests to ensure connection pooling works correctly.",
        stop_reason="tool_use", duration_ms=12000,
        files=["/app/tests/test_async_db.py"]))

    t += timedelta(seconds=14); s = 22; cum_in += 45000; cum_out += 400
    steps.append(step(SID_GOOD, s, t, 45000, 400, cum_in, cum_out,
        [tc("Bash", "command': 'cd /app && python -m pytest tests/ -v --tb=short'")],
        "Full suite: 38/38 passing. Task complete — async conversion, error handling, and tests all done.",
        stop_reason="end_turn", duration_ms=14000))

    return steps


if __name__ == "__main__":
    bad = generate_unprotected()
    with open("demos/unprotected.jsonl", "w") as f:
        for s in bad:
            f.write(json.dumps(s) + "\n")
    print(f"Wrote {len(bad)} steps to demos/unprotected.jsonl")

    good = generate_protected()
    with open("demos/protected.jsonl", "w") as f:
        for s in good:
            f.write(json.dumps(s) + "\n")
    print(f"Wrote {len(good)} steps to demos/protected.jsonl")

    # Also generate analysis JSON for both
    import sys
    sys.path.insert(0, ".")
    from analyzer import TrajectoryAnalyzer
    import tempfile, os

    for name, data in [("unprotected", bad), ("protected", good)]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            for s in data:
                tmp.write(json.dumps(s) + "\n")
            tmp_path = tmp.name
        try:
            analyzer = TrajectoryAnalyzer(tmp_path)
            analysis = analyzer.full_analysis()
            analysis["session_id"] = f"demo-{name}"
            with open(f"demos/{name}_analysis.json", "w") as f:
                json.dump(analysis, f, indent=2)
            print(f"  {name}: health={analysis['health_score']}, "
                  f"loops={len(analysis['anomalies']['loops'])}, "
                  f"spirals={len(analysis['anomalies']['error_spirals'])}, "
                  f"context_decay={len(analysis['anomalies']['context_decay'])}")
        finally:
            os.unlink(tmp_path)
