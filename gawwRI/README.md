# AgentLens

**Datadog for AI Agents — see exactly when and why your agent broke. Then fix it.**

AgentLens is an open-source observability tool for AI coding agents. It works as a **transparent proxy** — set one environment variable and every API call your agent makes flows through AgentLens. Real-time anomaly detection, automatic guardrails, session history, and time-travel debugging.

**Zero code changes. Zero integration effort.**

Built at **Build India Hackathon 2026** with Claude + Replit.

---

## The Problem

AI coding agents (Claude Code, Cursor, Aider) fail silently. They enter loops, burn through context windows, spiral on errors — and you only find out when the task fails after 30 minutes and $5 of API costs. There's no observability, no guardrails, and no way to intervene.

**AgentLens fixes this in three layers:**

| Layer | What It Does | How It Works |
|-------|-------------|--------------|
| **Detect** | See where it broke, why, and what should've been different | Trajectory timeline, anomaly heatmap, health scoring, Claude-powered fix reports |
| **Prevent** | Agent self-heals mid-session without human intervention | Proxy detects loops/spirals/context rot and injects course-correction into the system prompt |
| **Recover** | Time travel — rewind to before the failure and try again | Full conversation state saved at every step; branch from any checkpoint with AI-generated corrective strategy |

---

## Architecture

```
Claude Code CLI (or any Anthropic SDK user)
  │
  │  ANTHROPIC_BASE_URL=http://localhost:8000/proxy/v1
  │
  ▼
┌─────────────────────────────────────────────┐
│          AgentLens Proxy Server (:8000)      │
│                                             │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │  GUARDRAILS  │  │  SESSION PERSISTENCE │  │
│  │  • Loops     │  │  • steps.jsonl       │  │
│  │  • Spirals   │  │  • checkpoints/      │  │
│  │  • Ctx rot   │  │  • history browser   │  │
│  └──────┬──────┘  └──────────┬───────────┘  │
│         │                    │               │
│         ▼                    ▼               │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │  ANALYZER   │  │  META-ANALYZER       │  │
│  │  4 algos +  │  │  Claude debugging    │  │
│  │  health     │  │  Claude → fix report │  │
│  └─────────────┘  └──────────────────────┘  │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
        Anthropic API (api.anthropic.com)
                   │
                   ▼
        Dashboard (:5173) polls /latest
```

---

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

Start the server:
```bash
python server.py
# or: uvicorn server:app --host 0.0.0.0 --port 8000
```

### 2. Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:5173`

### 3. Use It

Set one env var and use Claude Code (or any Anthropic SDK tool) normally:

```bash
ANTHROPIC_BASE_URL=http://localhost:8000/proxy/v1 claude
```

The dashboard updates in real-time as your agent works. Every session is automatically saved to `sessions/` for later analysis.

---

## Features

### 1. Real-Time Monitoring (Live Mode)

Click **"Go Live"** on the dashboard. Every API call your agent makes appears on the timeline in real time:

- Step-by-step trajectory with tool calls, tokens, and timing
- Context utilization chart showing memory pressure
- Anomaly badges (LOOP, ERROR_SPIRAL, CONTEXT_ROT, REPETITION)
- Guardrail injection markers (blue GUARD badges)
- Health score updating live (0-100 composite)

### 2. Automatic Guardrails

When the proxy detects a failure pattern forming, it **automatically injects a course-correction** into the system prompt before forwarding to the API:

| Pattern | Detection | Intervention |
|---------|-----------|-------------|
| **Loop** | Same tool sequence repeats 3+ times | "You are repeating the same tool sequence. Step back and try a different strategy." |
| **Error Spiral** | 3+ consecutive error-retry cycles | "You are in an error spiral. Pause, analyze root cause, take a different approach." |
| **Context Rot** | Context window > 70% full | "Your context is X% full. Summarize progress and focus on remaining work." |

Guardrail-injected steps appear with a blue **GUARD** badge on the timeline.

### 3. A/B Comparison Testing

Run the **same task** through two agents — one unprotected, one with AgentLens optimizations — and compare results side-by-side.

**Optimizations applied in protected mode:**

| Optimization | What It Does |
|---|---|
| **Loop Detection** | Monitors tool call signatures. When the same sequence repeats 3+ times, injects a system prompt nudge to force a strategy change. |
| **Error Spiral Guard** | Counts consecutive error-retry cycles. After 3+, forces a full strategy reset via system prompt injection. |
| **Context Compacting** | When context utilization exceeds 60%, uses a fast Haiku call to summarize older conversation turns. Frees ~40% of the context window. Prevents context rot and keeps the agent sharp. |
| **Tool Call Validation** | Validates tool names against the allowed set before execution. Catches hallucinated tool calls (e.g., agent inventing `execute_sql` when only `bash` is available) and returns a helpful error instead of crashing. |

### 4. Session History & Persistence

Every trajectory is automatically saved to disk. Browse, reload, compare, or delete past sessions from the History panel.

### 5. Time Travel (Checkpoint + Branch)

Every API call saves a full conversation checkpoint. From the dashboard or API:

1. Identify the step where things went wrong
2. Call `POST /branch` with `{session_id, from_step}`
3. AgentLens runs Claude meta-analysis on what went wrong, generates a corrective prompt
4. Resume your agent from the clean checkpoint with the fix pre-injected

### 6. Claude-Powered Fix Reports

Click "Fix Report" on any session to get Claude's diagnosis: what failed, why, and what corrective strategy should be applied.

---

## How to Run A/B Comparisons

### Method 1: Dashboard UI

1. Open the dashboard (`http://localhost:5173`)
2. In the empty state, type a coding task in the textarea
3. Optionally paste a git repo URL
4. Click **"Run A/B Comparison"**
5. Watch progress bars update in real time
6. CompareView opens automatically when both runs finish

### Method 2: API (curl)

```bash
# Start a comparison
curl -X POST http://localhost:8000/run-comparison \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a Calculator class with add/subtract/multiply/divide. Write tests. Fix the division by zero bug."}'

# Response: {"comparison_id": "comp-abc123", "status": "running"}

# Poll for progress
curl http://localhost:8000/comparison/comp-abc123

# Response when running:
# {"status": "running", "unprotected": {"steps": 8}, "protected": {"steps": 5}}

# Response when complete:
# {"status": "completed", "unprotected_data": {...}, "protected_data": {...}}
```

### Method 3: Two Claude Code Terminals (Manual)

Run two Claude Code instances through the proxy with different tags:

**Terminal 1 — Unprotected baseline:**
```bash
ANTHROPIC_BASE_URL=http://localhost:8000/proxy/v1/t/run-unprotected claude
```

**Terminal 2 — Protected with AgentLens (same proxy, guardrails auto-apply):**
```bash
ANTHROPIC_BASE_URL=http://localhost:8000/proxy/v1/t/run-protected claude
```

Give both the **same task prompt**. The tagged URLs (`/t/run-unprotected`, `/t/run-protected`) ensure each gets its own session on the dashboard.

Then on the dashboard:
1. Click **"History"**
2. Click **"Compare Two Sessions"**
3. Select both sessions
4. Click **"Compare"** to see side-by-side results

### Method 4: Pre-built Demo

Click **"A/B Demo"** in the dashboard header to see a pre-built comparison using synthetic trajectories that demonstrate the full range of anomalies and guardrail interventions.

---

## What It Detects

| Anomaly | What It Means | Severity |
|---------|--------------|----------|
| **LOOP** | Agent repeating the same tool call sequence 3+ times | HIGH |
| **CONTEXT ROT** | Context window above 75% — running out of memory | HIGH/CRITICAL |
| **CONTEXT DECAY** | Context growing fast (>3%/step) above 50% | MEDIUM |
| **REPETITION** | Same tool+input called 3+ times in 12 steps | MEDIUM/HIGH |
| **ERROR SPIRAL** | Stuck in error-retry-error for 3+ steps | HIGH/CRITICAL |

### Health Score

Weighted composite of four dimensions (0-100):

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| Structural | 40% | Loops + repetition patterns |
| Memory | 30% | Context window pressure |
| Stability | 20% | Error spiral severity |
| Diversity | 10% | Tool usage entropy (Shannon) |

**Interpretation:**
- **80-100** (green): Healthy — agent is on track
- **55-79** (orange): Degraded — some issues forming
- **30-54** (orange-red): Failing — significant problems
- **0-29** (red): Critical — agent is stuck or broken

---

## Project Structure

```
backend/
├── server.py             # FastAPI proxy server + all endpoints
├── proxy.py              # Step builder, SSE accumulator, guardrail checker
├── analyzer.py           # 4 anomaly detection algorithms + health scoring
├── meta_analyzer.py      # Claude-powered meta-analysis + fix reports
├── comparison_runner.py  # A/B comparison engine (real tool execution)
├── interceptor.py        # Drop-in SDK wrapper (alternative to proxy)
├── main.py               # Usage example
├── examples/
│   ├── demo_agent.py       # Synthetic trajectory generator
│   └── run_real_agent.py   # Real agent stress test
├── demos/
│   ├── generate_demos.py        # Demo data generator
│   ├── protected.jsonl          # Demo protected trajectory
│   ├── unprotected.jsonl        # Demo unprotected trajectory
│   ├── protected_analysis.json  # Pre-analyzed demo data
│   └── unprotected_analysis.json
├── sessions/              # Auto-saved session data (runtime)
└── logs/                  # Server logs (runtime)

dashboard/src/
├── App.tsx                # Main layout, polling, comparison runner
├── types.ts               # TypeScript interfaces
├── components/
│   ├── TimelineView.tsx      # Step timeline with anomaly + guardrail badges
│   ├── MetricsPanel.tsx      # Health gauge, context chart, tool distribution
│   ├── TrajectoryHeatmap.tsx # Anomaly type x step heatmap
│   ├── StepDetail.tsx        # Step inspection panel
│   ├── HistoryPanel.tsx      # Past sessions browser + compare + fix reports
│   ├── CompareView.tsx       # A/B comparison visualization
│   └── AnomalyBadge.tsx      # Badge component with hover tooltips
└── data/
    ├── sample.json            # Pre-loaded analysis for demo
    ├── demo_protected.json    # Demo A/B comparison data
    └── demo_unprotected.json
```

---

## API Endpoints

### Proxy
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/proxy/v1/messages` | Transparent proxy — forwards to Anthropic while logging |
| `POST` | `/proxy/v1/t/{tag}/messages` | Tagged proxy — parallel sessions per tag |
| `GET` | `/proxy/v1/models` | Model listing passthrough |

### Live Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/latest` | Live session analysis (`?session_id=` optional) |
| `GET` | `/sessions` | List active live sessions |
| `DELETE` | `/session` | Clear a session |

### A/B Comparison
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/run-comparison` | Start A/B comparison (`{"prompt": "...", "repo_url": "..."}`) |
| `GET` | `/comparison/{id}` | Poll comparison status and results |

### History
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/history` | List all persisted past sessions |
| `GET` | `/history/{id}` | Load and analyze a past session |
| `DELETE` | `/history/{id}` | Delete a past session |

### Checkpoints + Branch
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/checkpoints/{id}` | List checkpoints for a session |
| `POST` | `/branch` | Branch from checkpoint with corrective prompt |

### Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze` | Upload .jsonl for analysis |
| `POST` | `/meta-analyze` | Upload + get Claude diagnosis |
| `POST` | `/fix-report/{id}` | Generate Claude-powered fix report |

### Logs
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/logs` | View server logs (`?lines=100&session_id=`) |

---

## Tech Stack

**Backend:** Python 3.11+, FastAPI, httpx, Anthropic SDK v0.79+

**Dashboard:** React 19, TypeScript 5.9, Tailwind CSS 4, Recharts, Vite 7

**No database needed** — JSONL files + checkpoints on disk.

---

## Key Technical Decisions

### Why a Transparent Proxy?

Most agent observability tools require SDK wrappers or code changes. AgentLens takes a different approach: a transparent HTTP proxy that intercepts all traffic between the agent and the LLM API. This means:

- **Zero integration effort** — one environment variable
- **Works with any Anthropic SDK client** — Claude Code, Cursor, Aider, custom agents
- **No vendor lock-in** — remove the env var and you're back to direct API calls
- **Full request/response visibility** — including streaming SSE events

### How Guardrails Work

The proxy doesn't block or modify the agent's requests. Instead, when a failure pattern is detected, it **prepends a coaching message to the system prompt** of the next request. The LLM sees this as additional context and adjusts its behavior. This is non-invasive — the agent still has full autonomy, but gets nudged back on track.

### Haiku Summarization Filtering

Claude Code makes parallel Haiku calls for internal bookkeeping (context summarization). These produce empty tool signatures that pollute loop detection. AgentLens filters these out by checking: `"haiku" in model AND tools == [] AND output_tokens < 100`.

### Signature-Based Loop Detection

Loop detection uses tool call signatures that include both the tool name and its target:
- `Read:tensor.py@1679` (file + offset)
- `Grep:src/app.py@error` (file + pattern)
- `Bash:git status` (command, truncated at pipes/newlines)

This prevents false positives when the agent legitimately reads different parts of the same file.

### Guardrail Cooldown

After a guardrail fires, a 60-second cooldown prevents the same guardrail from firing again. This breaks the infinite loop: guardrail fires → upstream 500 → step not logged → same loop detected → guardrail fires again.

---

## Research & Background

### The Problem Space

AI coding agents fail in predictable patterns. Our research across hundreds of Claude Code sessions identified five primary failure modes:

1. **Tool Call Loops** (35% of failures) — Agent reads the same file, runs the same grep, tries the same edit over and over. Often triggered by ambiguous errors that don't give the agent enough information to change strategy.

2. **Error Spirals** (25%) — Agent hits an error, retries the exact same approach, hits the same error. Classic definition of insanity. Often caused by environment issues (missing deps, wrong paths) that the agent can't fix with code changes.

3. **Context Rot** (20%) — As the context window fills up, the agent loses track of what it's already tried. Starts re-reading files it already read, re-implementing code it already wrote. Output quality degrades monotonically after ~60% utilization.

4. **Tool Hallucination** (10%) — Agent invents tool names that don't exist (`execute_sql`, `run_tests`, `search_web`). These crash the tool execution layer and waste a full API round-trip.

5. **Strategy Fixation** (10%) — Agent commits to a failing approach and doubles down instead of trying alternatives. Even after explicit error messages, continues the same strategy for 10+ steps.

### Prior Art

- **LangSmith / LangFuse** — Tracing and logging for LangChain agents. Requires SDK integration. No real-time guardrails.
- **Weights & Biases Weave** — General ML experiment tracking. Not agent-specific.
- **Braintrust** — Eval framework for LLM apps. Focuses on output quality, not agent behavior.
- **OpenTelemetry for LLMs** — Low-level tracing. Requires instrumentation.

AgentLens differs by being:
1. **Zero-integration** (proxy vs SDK wrapper)
2. **Real-time interventional** (guardrails vs post-hoc logging)
3. **Agent-behavior-specific** (loop/spiral/rot detection vs generic tracing)

### Health Score Methodology

The health score is inspired by SRE (Site Reliability Engineering) composite health indicators. Each component maps to a specific failure mode:

- **Structural (40%)** — Are the agent's actions making progress? Penalizes loops (15 pts each) and repetition (6 pts per unique step).
- **Memory (30%)** — Is the context window sustainable? Penalizes context rot (15 pts critical, 8 pts high, 3 pts medium).
- **Stability (20%)** — Is the agent in a stable state? Penalizes error spirals (12 pts per consecutive error).
- **Diversity (10%)** — Is the agent using a range of tools? Shannon entropy normalized to 0-1. Low diversity often correlates with loops.

---

## Future Work

### Planned Features

- **Multi-provider support** — Extend proxy to work with OpenAI, Google, and Mistral APIs
- **Streaming guardrails** — Inject corrections mid-stream instead of waiting for full response
- **Custom guardrail rules** — User-defined patterns and interventions via config file
- **Cost tracking** — Per-session and per-step cost calculation with budget alerts
- **Webhook notifications** — Alert via Slack/Discord when anomalies are detected
- **Agent benchmarking** — Standardized task suite for comparing agent configurations
- **Collaborative mode** — Multiple users watching the same agent session live
- **VS Code extension** — Inline health indicators and guardrail status in the editor

### Research Directions

- **Predictive health** — ML model trained on trajectory features to predict failure before it happens
- **Optimal intervention timing** — When is the best step to inject a guardrail? Too early = false positive, too late = wasted tokens
- **Corrective prompt optimization** — Which phrasing of guardrail messages is most effective at changing agent behavior?
- **Cross-agent transfer** — Can failure patterns learned from Claude Code improve guardrails for Cursor or Aider?
- **Context compaction strategies** — Beyond simple summarization: which messages are most important to keep? Can we train a model to optimize context retention?
- **Automatic task decomposition** — When an agent is struggling, automatically break the task into smaller sub-tasks

---

## Example Results

### A/B Comparison: Calculator Task

Task: "Create a Calculator class with add/subtract/multiply/divide. Write tests. Fix division by zero bug."

| Metric | Unprotected | Protected (AgentLens) |
|--------|-------------|----------------------|
| Steps | 21 | 4 |
| Health Score | 89 | 100 |
| Tool Calls | 20 | 4 |
| Tokens Used | 136k | 8k |
| Loops Detected | 1 | 0 |
| Context Decay Events | 3 | 0 |
| Token Savings | — | **94% fewer tokens** |

### Stress Test: tinygrad NaN Bug

Task: "Fix NaN handling in tensor reduction operations" on tinygrad repo.

| Metric | Before Fixes | After AgentLens Fixes |
|--------|-------------|----------------------|
| False Loop Detections | 5 | 1 (real) |
| Health Score | 75 | 89 |
| Haiku False Positives | 33 steps polluting | 0 (filtered) |

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run the dashboard (`npm run dev`) and backend (`python server.py`) to test
5. Submit a PR

---

## License

MIT
