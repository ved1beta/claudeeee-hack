"""
AgentLens Comparison Runner — runs two parallel agent loops (unprotected vs protected)
against the same task with real tool execution.

The protected run applies:
1. Loop detection + guardrail injection
2. Error spiral detection + guardrail injection
3. Context compacting (summarize old messages when context > 60%)
4. Tool call validation (catch hallucinated tool names)
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from datetime import datetime

import anthropic
from proxy import check_guardrails, new_session_state, build_step_entry, CONTEXT_WINDOW_MAX
from analyzer import TrajectoryAnalyzer

# ─── Tool Definitions ─────────────────────────────────────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file's contents. Returns the full text of the file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a shell command and return stdout + stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "grep",
        "description": "Search for a pattern across files. Returns matching lines with file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "path": {"type": "string", "description": "Directory or file to search"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory recursively (up to 3 levels deep).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: .)"},
            },
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}


# ─── Real Tool Execution ──────────────────────────────────────────────

def execute_tool(name: str, input_data: dict, sandbox_dir: str) -> str:
    """Execute a tool call with real filesystem/subprocess operations."""

    if name == "read_file":
        path = os.path.join(sandbox_dir, input_data.get("path", ""))
        path = os.path.realpath(path)
        if not path.startswith(os.path.realpath(sandbox_dir)):
            return "Error: path escapes sandbox directory"
        try:
            with open(path) as f:
                content = f.read()
            # Truncate very large files
            if len(content) > 10000:
                return content[:10000] + f"\n\n... [truncated, {len(content)} total chars]"
            return content
        except FileNotFoundError:
            return f"Error: file not found: {input_data.get('path', '')}"
        except Exception as e:
            return f"Error reading file: {e}"

    elif name == "write_file":
        path = os.path.join(sandbox_dir, input_data.get("path", ""))
        path = os.path.realpath(path)
        if not path.startswith(os.path.realpath(sandbox_dir)):
            return "Error: path escapes sandbox directory"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(input_data.get("content", ""))
            return f"File written: {input_data.get('path', '')}"
        except Exception as e:
            return f"Error writing file: {e}"

    elif name == "bash":
        command = input_data.get("command", "")
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=sandbox_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if not output:
                output = f"(exit code {result.returncode})"
            # Truncate
            if len(output) > 5000:
                output = output[:5000] + "\n... [truncated]"
            return output
        except subprocess.TimeoutExpired:
            return "Error: command timed out after 30 seconds"
        except Exception as e:
            return f"Error: {e}"

    elif name == "grep":
        pattern = input_data.get("pattern", "")
        search_path = input_data.get("path", ".")
        full_path = os.path.join(sandbox_dir, search_path)
        full_path = os.path.realpath(full_path)
        if not full_path.startswith(os.path.realpath(sandbox_dir)):
            return "Error: path escapes sandbox directory"
        try:
            result = subprocess.run(
                ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.js",
                 "--include=*.json", "--include=*.md", "--include=*.txt",
                 "--include=*.yaml", "--include=*.yml", "--include=*.toml",
                 pattern, full_path],
                capture_output=True, text=True, timeout=15,
            )
            output = result.stdout or "No matches found."
            if len(output) > 5000:
                output = output[:5000] + "\n... [truncated]"
            return output
        except subprocess.TimeoutExpired:
            return "Error: grep timed out"
        except Exception as e:
            return f"Error: {e}"

    elif name == "list_files":
        dir_path = input_data.get("path", ".")
        full_path = os.path.join(sandbox_dir, dir_path)
        full_path = os.path.realpath(full_path)
        if not full_path.startswith(os.path.realpath(sandbox_dir)):
            return "Error: path escapes sandbox directory"
        try:
            files = []
            for root, dirs, filenames in os.walk(full_path):
                # Limit depth to 3
                depth = root[len(full_path):].count(os.sep)
                if depth >= 3:
                    dirs.clear()
                    continue
                # Skip hidden dirs and common noise
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git", "venv", ".venv")]
                for fname in filenames:
                    if not fname.startswith("."):
                        rel = os.path.relpath(os.path.join(root, fname), full_path)
                        files.append(rel)
            return "\n".join(sorted(files)[:200]) or "(empty directory)"
        except Exception as e:
            return f"Error: {e}"

    return f"Error: unknown tool '{name}'"


# ─── Context Compacting ───────────────────────────────────────────────

def compact_messages(messages: list, client: anthropic.Anthropic) -> list:
    """Summarize older messages to free context space.

    Keeps the first user message and last 4 messages intact.
    Summarizes everything in between into a single assistant message.
    """
    if len(messages) <= 6:
        return messages

    first_msg = messages[0]  # original user prompt
    middle = messages[1:-4]
    recent = messages[-4:]

    # Build summary of middle messages
    summary_parts = []
    for msg in middle:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract tool use/result info
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        summary_parts.append(f"- Called {block.get('name', '?')}({str(block.get('input', ''))[:80]})")
                    elif block.get("type") == "tool_result":
                        result_text = str(block.get("content", ""))[:100]
                        summary_parts.append(f"  Result: {result_text}")
                    elif block.get("type") == "text":
                        text = block.get("text", "")[:150]
                        if text:
                            summary_parts.append(f"- [{role}]: {text}")
        elif isinstance(content, str) and content:
            summary_parts.append(f"- [{role}]: {content[:150]}")

    if not summary_parts:
        return messages

    # Use Haiku to compress
    summary_text = "\n".join(summary_parts[:50])
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"Summarize this agent work log in 3-5 bullet points. Focus on what was accomplished and what problems were found:\n\n{summary_text}",
            }],
        )
        compact_text = resp.content[0].text if resp.content else "Previous work summarized."
    except Exception:
        compact_text = f"[Previous {len(middle)} conversation turns compacted. Key actions: {summary_text[:300]}]"

    # Rebuild messages: original prompt + summary + recent
    return [
        first_msg,
        {"role": "assistant", "content": f"[Context compacted by AgentLens] Here's what I've done so far:\n{compact_text}\n\nContinuing with the task..."},
        {"role": "user", "content": "Continue. Pick up where you left off."},
    ] + recent


# ─── Agent Loop ───────────────────────────────────────────────────────

def run_agent_loop(
    prompt: str,
    sandbox_dir: str,
    session_id: str,
    protected: bool = False,
    max_steps: int = 30,
    on_step=None,
) -> dict:
    """Run a single agent loop. Returns analysis dict.

    Args:
        prompt: The task for the agent
        sandbox_dir: Working directory for tool execution
        session_id: Session ID for tracking
        protected: Whether to apply AgentLens optimizations
        max_steps: Maximum number of steps
        on_step: Callback(step_num, step_entry) called after each step
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    system = """You are an expert software engineer working autonomously. You have access to tools: read_file, write_file, bash, grep, list_files.

CRITICAL RULES:
- NEVER ask for confirmation or permission. NEVER ask "should I proceed?" or "would you like me to...". Just do it.
- NEVER stop to ask clarifying questions. Make your best judgment and proceed.
- If you encounter an error, try a different approach immediately. Do not ask for help.
- If no files exist yet, create them yourself to complete the task.

Your approach:
1. First explore the codebase structure (list_files, read key files)
2. Understand the architecture and identify issues
3. Make changes to fix problems
4. Test your changes with bash
5. Iterate until the task is complete

Be thorough and methodical. Only use the tools listed above."""

    messages = [{"role": "user", "content": prompt}]

    # Tracking state (reuse proxy.py structures for guardrail compatibility)
    state = new_session_state(session_id)
    steps = []
    optimizations_applied = {
        "loop_detection": 0,
        "error_spiral": 0,
        "context_compacting": 0,
        "tool_validation": 0,
    }

    for step_num in range(1, max_steps + 1):
        # --- Protected: Check guardrails ---
        active_system = system
        if protected and len(steps) >= 3:
            guardrail = check_guardrails(steps, state)
            if guardrail:
                active_system = guardrail["message"] + "\n\n" + system
                if guardrail["type"] == "LOOP":
                    optimizations_applied["loop_detection"] += 1
                elif guardrail["type"] == "ERROR_SPIRAL":
                    optimizations_applied["error_spiral"] += 1
                elif guardrail["type"] == "CONTEXT_ROT":
                    pass  # handled by context compacting below
                state["last_guardrail"] = guardrail["type"]

        # --- Protected: Context compacting ---
        if protected:
            token_est = state["cumulative_input_tokens"]
            if token_est > CONTEXT_WINDOW_MAX * 0.6 and len(messages) > 6:
                messages = compact_messages(messages, client)
                optimizations_applied["context_compacting"] += 1
                state["last_guardrail"] = "CONTEXT_COMPACT"

        # --- Make API call ---
        start_time = time.time()
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=active_system,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            # Log error step and break
            break

        duration_ms = (time.time() - start_time) * 1000
        state["last_step_duration_ms"] = round(duration_ms)

        # Build response dict for step entry
        response_dict = {
            "content": [],
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "stop_reason": response.stop_reason,
        }
        for block in response.content:
            if block.type == "text":
                response_dict["content"].append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                response_dict["content"].append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input if isinstance(block.input, dict) else {},
                })

        # Build request dict
        request_dict = {
            "model": "claude-sonnet-4-5-20250929",
            "messages": messages,
            "tools": TOOLS,
            "system": active_system,
        }

        step_entry = build_step_entry(request_dict, response_dict, state)
        steps.append(step_entry)

        if on_step:
            on_step(step_num, step_entry)

        # Add assistant response to messages
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input if isinstance(block.input, dict) else {},
                })
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "end_turn":
            break

        # --- Execute tool calls ---
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input if isinstance(block.input, dict) else {}

                # Protected: Tool call validation
                if protected and tool_name not in TOOL_NAMES:
                    optimizations_applied["tool_validation"] += 1
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: '{tool_name}' is not a valid tool. Available tools: {', '.join(sorted(TOOL_NAMES))}",
                        "is_error": True,
                    })
                    continue

                result = execute_tool(tool_name, tool_input, sandbox_dir)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    # --- Analyze trajectory ---
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        for s in steps:
            tmp.write(json.dumps(s) + "\n")
        tmp_path = tmp.name

    try:
        analyzer = TrajectoryAnalyzer(tmp_path)
        analysis = analyzer.full_analysis()
    finally:
        os.unlink(tmp_path)

    analysis["session_id"] = session_id
    analysis["optimizations_applied"] = optimizations_applied
    return analysis


# ─── Comparison Runner ────────────────────────────────────────────────

# In-memory storage for comparison state
comparisons: dict[str, dict] = {}


async def run_comparison(prompt: str, repo_url: str | None = None) -> str:
    """Start a comparison run. Returns comparison_id."""
    comp_id = f"comp-{uuid.uuid4().hex[:8]}"

    comparisons[comp_id] = {
        "status": "running",
        "prompt": prompt,
        "started_at": datetime.utcnow().isoformat(),
        "unprotected": {"status": "running", "steps": 0, "health": None, "data": None},
        "protected": {"status": "running", "steps": 0, "health": None, "data": None},
    }

    # Create sandbox directories
    base_dir = f"/tmp/agentlens-{comp_id}"
    unprotected_dir = f"{base_dir}/unprotected"
    protected_dir = f"{base_dir}/protected"
    os.makedirs(unprotected_dir, exist_ok=True)
    os.makedirs(protected_dir, exist_ok=True)

    # If repo_url provided, clone into both dirs
    if repo_url:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, unprotected_dir],
                timeout=60, capture_output=True,
            )
            # Copy to protected dir
            shutil.copytree(unprotected_dir, protected_dir, dirs_exist_ok=True)
        except Exception as e:
            comparisons[comp_id]["status"] = "failed"
            comparisons[comp_id]["error"] = f"Failed to clone repo: {e}"
            return comp_id
    else:
        # Create a basic workspace with a README
        for d in [unprotected_dir, protected_dir]:
            with open(os.path.join(d, "README.md"), "w") as f:
                f.write("# Workspace\nThis is the agent's working directory.\n")

    # Run both loops in parallel
    loop = asyncio.get_event_loop()

    def run_unprotected():
        def on_step(n, entry):
            comparisons[comp_id]["unprotected"]["steps"] = n
        try:
            result = run_agent_loop(
                prompt=prompt,
                sandbox_dir=unprotected_dir,
                session_id=f"compare-unprotected-{comp_id}",
                protected=False,
                max_steps=30,
                on_step=on_step,
            )
            comparisons[comp_id]["unprotected"]["data"] = result
            comparisons[comp_id]["unprotected"]["health"] = result["health_score"]
            comparisons[comp_id]["unprotected"]["status"] = "completed"
        except Exception as e:
            comparisons[comp_id]["unprotected"]["status"] = "failed"
            comparisons[comp_id]["unprotected"]["error"] = str(e)

    def run_protected():
        def on_step(n, entry):
            comparisons[comp_id]["protected"]["steps"] = n
        try:
            result = run_agent_loop(
                prompt=prompt,
                sandbox_dir=protected_dir,
                session_id=f"compare-protected-{comp_id}",
                protected=True,
                max_steps=30,
                on_step=on_step,
            )
            comparisons[comp_id]["protected"]["data"] = result
            comparisons[comp_id]["protected"]["health"] = result["health_score"]
            comparisons[comp_id]["protected"]["status"] = "completed"
        except Exception as e:
            comparisons[comp_id]["protected"]["status"] = "failed"
            comparisons[comp_id]["protected"]["error"] = str(e)

    async def run_both():
        # Run in thread pool since anthropic SDK is synchronous
        await asyncio.gather(
            loop.run_in_executor(None, run_unprotected),
            loop.run_in_executor(None, run_protected),
        )
        comparisons[comp_id]["status"] = "completed"
        comparisons[comp_id]["completed_at"] = datetime.utcnow().isoformat()

    asyncio.create_task(run_both())
    return comp_id


def get_comparison_status(comp_id: str) -> dict | None:
    """Get current status of a comparison run."""
    return comparisons.get(comp_id)
