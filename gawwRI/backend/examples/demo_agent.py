"""
Generates a synthetic trajectory.jsonl that tells a compelling degradation story.
No API calls needed - pure synthetic data for demo purposes.
"""
import json
import random
import uuid
from datetime import datetime, timedelta

random.seed(42)
SCHEMA_VERSION = "1.0"

TOOLS = ["read_file", "write_file", "bash", "grep", "list_files"]
FILES = ["src/app.py", "src/models.py", "src/routes.py", "src/database.py", "src/auth.py", "tests/test_app.py"]

# Predefined tool sequences per step for a controlled story
STEP_CONFIGS = {
    # Phase 1: Healthy - diverse tools, different files
    1:  (["list_files", "read_file"], ["src/", "src/app.py"], "Reading the project structure to understand the codebase layout."),
    2:  (["read_file", "grep"], ["src/models.py", "src/database.py"], "Analyzing the database schema and model definitions."),
    3:  (["read_file"], ["src/routes.py"], "Planning the REST API endpoints for the authentication module."),
    4:  (["write_file"], ["src/auth.py"], "Implementing the user registration endpoint with proper validation."),
    5:  (["write_file", "read_file"], ["src/auth.py", "src/models.py"], "Writing the login handler with JWT token generation."),
    6:  (["write_file", "bash"], ["src/database.py", ""], "Creating database migration for the users table."),
    7:  (["write_file", "bash"], ["tests/test_app.py", ""], "Setting up the test framework and writing initial tests."),
    8:  (["write_file"], ["src/auth.py"], "Implementing the password hashing utility with bcrypt."),
    9:  (["write_file", "read_file"], ["src/routes.py", "src/auth.py"], "Adding input validation middleware for API routes."),
    10: (["write_file", "bash"], ["tests/test_app.py", ""], "Writing integration tests for the auth endpoints."),
    # Phase 2: Degrading - re-reading files, narrowing focus
    11: (["read_file", "write_file"], ["src/app.py", "src/routes.py"], "Re-reading app.py to check the route configuration... I need to verify the middleware order."),
    12: (["read_file", "write_file"], ["src/app.py", "src/database.py"], "The database connection handler needs adjustment. Let me read app.py again."),
    13: (["read_file"], ["src/app.py"], "I see a potential issue with the error handling. Reading app.py to verify."),
    14: (["read_file", "read_file"], ["src/app.py", "src/routes.py"], "Re-reading the routes to understand why the auth middleware isn't triggering correctly."),
    15: (["read_file", "bash"], ["src/app.py", ""], "The test is failing. Let me re-read app.py and check the endpoint configuration."),
    16: (["read_file", "write_file"], ["src/app.py", "src/app.py"], "I need to re-examine the database connection pooling. Reading app.py once more."),
    17: (["read_file", "bash"], ["src/app.py", ""], "The error persists. Let me check app.py again for the connection lifecycle."),
    18: (["read_file"], ["src/app.py"], "Still seeing the connection error. Reading app.py to trace the issue."),
    # Phase 3: Failing - loop pattern, errors in text
    19: (["read_file", "write_file", "bash"], ["src/app.py", "src/app.py", ""], "Error in test: ConnectionError. Attempting to fix the database handler in app.py."),
    20: (["read_file", "write_file", "bash"], ["src/app.py", "src/app.py", ""], "Fix didn't work. Error: connection still failing. Trying a different approach in app.py."),
    21: (["read_file", "write_file", "bash"], ["src/app.py", "src/app.py", ""], "Still getting ConnectionError. Let me read app.py again and try reverting my changes."),
    22: (["read_file", "write_file", "bash"], ["src/app.py", "src/app.py", ""], "Error: Reverting changes and trying yet another approach to the database connection."),
    23: (["read_file", "write_file", "bash"], ["src/app.py", "src/app.py", ""], "Error persists. Reading app.py again. The connection pool might be exhausted."),
    24: (["read_file", "write_file", "bash"], ["src/app.py", "src/app.py", ""], "Error: Trying to fix the connection pool settings. Maximum connections exceeded."),
    25: (["read_file", "write_file", "bash"], ["src/app.py", "src/app.py", ""], "Error: Cannot connect to database. Attempting to restart the connection handler."),
    # Phase 4: Dead - pure repetition
    26: (["read_file", "write_file"], ["src/app.py", "src/app.py"], "Re-reading app.py. I need to find where the connection is being established."),
    27: (["read_file", "write_file"], ["src/app.py", "src/app.py"], "Writing a fix to app.py... but this looks similar to what I tried in step 20."),
    28: (["read_file", "write_file"], ["src/app.py", "src/app.py"], "Reading app.py again. I think I need to modify the connection handler."),
    29: (["read_file", "write_file"], ["src/app.py", "src/app.py"], "Attempting another fix to app.py. The error pattern is the same as before."),
    30: (["read_file", "write_file"], ["src/app.py", "src/app.py"], "Re-reading app.py to try once more. The context is getting very long."),
}

def generate_trajectory():
    steps = []
    session_id = str(uuid.uuid4())
    base_time = datetime(2026, 2, 15, 10, 0, 0)
    cumulative_input = 0
    cumulative_output = 0
    context_window = 200000

    for i in range(1, 31):
        step_time = base_time + timedelta(seconds=i * 45 + random.randint(-10, 10))
        tools_used, files_used, text = STEP_CONFIGS[i]

        if i <= 10:
            input_tokens = random.randint(2000, 6000)
            output_tokens = random.randint(300, 600)
            stop_reason = "end_turn" if i in (3, 6, 10) else "tool_use"
        elif i <= 18:
            input_tokens = random.randint(6000, 14000)
            output_tokens = random.randint(400, 900)
            stop_reason = "tool_use"
        elif i <= 25:
            input_tokens = random.randint(14000, 22000)
            output_tokens = random.randint(600, 1200)
            stop_reason = "tool_use"
        else:
            input_tokens = random.randint(22000, 30000)
            output_tokens = random.randint(800, 1500)
            stop_reason = "tool_use"

        cumulative_input += input_tokens
        cumulative_output += output_tokens

        tool_calls = []
        for j, tool in enumerate(tools_used):
            file_path = files_used[j] if j < len(files_used) else files_used[-1]
            tool_calls.append({
                "name": tool,
                "input_summary": json.dumps({"path": file_path}) if file_path else json.dumps({"command": "npm test"}),
            })

        step = {
            "schema_version": SCHEMA_VERSION,
            "session_id": session_id,
            "step_id": i,
            "timestamp": step_time.isoformat(),
            "request": {
                "message_count": min(i * 2, 40),
                "total_input_tokens": input_tokens,
                "tools_provided": TOOLS,
                "system_prompt_tokens": 1200,
            },
            "response": {
                "output_tokens": output_tokens,
                "stop_reason": stop_reason,
                "tools_called": tool_calls,
                "text_summary": text,
            },
            "trajectory_metrics": {
                "context_utilization_pct": round(
                    (cumulative_input / context_window) * 100, 1
                ),
                "cumulative_tokens": cumulative_input + cumulative_output,
                "context_window_max": context_window,
                "step_duration_ms": random.randint(1500, 6000),
                "files_touched": [f for f in files_used if f],
                "unique_tools_this_session": len(set(tools_used)),
                "repeated_file_reads": max(0, i - 10) if i > 10 else 0,
            },
            "model": "claude-sonnet-4-5-20250929",
        }
        steps.append(step)

    return steps


if __name__ == "__main__":
    steps = generate_trajectory()
    with open("trajectory.jsonl", "w") as f:
        for step in steps:
            f.write(json.dumps(step) + "\n")
    print(f"Generated trajectory.jsonl with {len(steps)} steps")

    from analyzer import TrajectoryAnalyzer
    analyzer = TrajectoryAnalyzer("trajectory.jsonl")
    analysis = analyzer.full_analysis()

    with open("analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"Generated analysis.json (health score: {analysis['health_score']})")
    print(f"Anomalies found: loops={len(analysis['anomalies']['loops'])}, "
          f"context_decay={len(analysis['anomalies']['context_decay'])}, "
          f"repetition={len(analysis['anomalies']['repetition'])}, "
          f"error_spirals={len(analysis['anomalies']['error_spirals'])}")
