import json
from collections import deque


class TrajectoryAnalyzer:
    def __init__(self, trajectory_path):
        self.steps = []
        with open(trajectory_path) as f:
            for line in f:
                self.steps.append(json.loads(line))

    def _tool_signature(self, tc):
        """Build a signature for a tool call including its target to avoid false positives.

        Includes enough context to distinguish:
        - Read same file at different offsets
        - Grep same file with different patterns
        - Bash running different commands
        """
        name = tc.get("name", "")
        input_sum = tc.get("input_summary", "")
        target = ""
        for prefix in ["file_path': '", 'file_path": "', "path': '", 'path": "', "command': '", 'command": "']:
            idx = input_sum.find(prefix)
            if idx >= 0:
                start = idx + len(prefix)
                close_char = prefix[-1]
                end = input_sum.find(close_char, start)
                if end < 0:
                    end = min(start + 80, len(input_sum))
                target = input_sum[start:end]
                # For commands, normalize by keeping only the first meaningful part
                if "command" in prefix:
                    for sep in ["\n", "\\n", " | ", " && ", " 2>&1"]:
                        cut = target.find(sep)
                        if cut > 0:
                            target = target[:cut]
                            break
                break

        # Add secondary differentiator for file operations
        # (offset for Read, pattern for Grep) to avoid false positives
        # when the same file is accessed with different params
        extra = ""
        for secondary in ["offset': ", "pattern': '", 'pattern": "']:
            idx = input_sum.find(secondary)
            if idx >= 0:
                start = idx + len(secondary)
                end = min(start + 30, len(input_sum))
                for ch in ["'", '"', ",", "}"]:
                    cut = input_sum.find(ch, start)
                    if 0 <= cut < end:
                        end = cut
                extra = input_sum[start:end].strip()
                break

        if target and extra:
            return f"{name}:{target}@{extra}"
        elif target:
            return f"{name}:{target}"
        return name

    def _is_summarization_step(self, step):
        """Check if a step is a Haiku summarization call (not a real agent step)."""
        model = step.get("model", "")
        tools = step.get("response", {}).get("tools_called", [])
        output_tokens = step.get("response", {}).get("output_tokens", 0)
        return "haiku" in model and len(tools) == 0 and output_tokens < 100

    def detect_loops(self, min_repeat=3):
        """Detect repeated sequences of tool calls. Deduplicates overlapping detections."""
        # Filter out Haiku summarization steps — they are internal Claude Code
        # bookkeeping and create empty signatures that pollute loop detection
        real_steps = [s for s in self.steps if not self._is_summarization_step(s)]

        signatures = []
        step_ids = []
        for step in real_steps:
            tools = step.get("response", {}).get("tools_called", [])
            sig = "|".join(self._tool_signature(tc) for tc in tools)
            if sig:  # skip steps with no tools (text-only responses)
                signatures.append(sig)
                step_ids.append(step["step_id"])

        # Find all loops, then keep only the longest non-overlapping ones
        raw = []
        for i in range(len(signatures)):
            for seq_len in range(1, 5):
                if i + seq_len * min_repeat > len(signatures):
                    break
                pattern = signatures[i:i + seq_len]
                repeats = 0
                for j in range(min_repeat):
                    if signatures[i + j * seq_len:i + (j + 1) * seq_len] == pattern:
                        repeats += 1
                    else:
                        break
                if repeats >= min_repeat:
                    start = step_ids[i]
                    end = step_ids[min(i + seq_len * repeats - 1, len(step_ids) - 1)]
                    raw.append((start, end, "|".join(pattern)))

        # Deduplicate: keep longest span for overlapping ranges
        raw.sort(key=lambda x: -(x[1] - x[0]))
        used = set()
        anomalies = []
        for start, end, pattern in raw:
            step_range = set(range(start, end + 1))
            if step_range & used:
                continue
            used |= step_range
            anomalies.append({
                "type": "LOOP",
                "start_step": start,
                "end_step": end,
                "pattern": pattern,
                "severity": "HIGH",
            })
        return anomalies

    def detect_context_decay(self, warning_threshold=50, critical_threshold=75):
        """Flag when context utilization is growing too fast."""
        anomalies = []
        for i in range(1, len(self.steps)):
            cur = self.steps[i].get("trajectory_metrics", {}).get("context_utilization_pct", 0)
            prev = self.steps[i - 1].get("trajectory_metrics", {}).get("context_utilization_pct", 0)
            rate = cur - prev

            if cur > critical_threshold:
                anomalies.append({
                    "type": "CONTEXT_ROT",
                    "step_id": self.steps[i]["step_id"],
                    "utilization": cur,
                    "rate": round(rate, 2),
                    "severity": "CRITICAL" if cur > 85 else "HIGH",
                })
            elif cur > warning_threshold and rate > 3:
                anomalies.append({
                    "type": "CONTEXT_DECAY",
                    "step_id": self.steps[i]["step_id"],
                    "utilization": cur,
                    "rate": round(rate, 2),
                    "severity": "MEDIUM",
                })
        return anomalies

    def detect_repetition(self, threshold=3, window=12):
        """Detect repeated identical tool calls."""
        anomalies = []
        recent = deque(maxlen=window)
        seen_at_step = {}  # avoid flagging same tool multiple times per step
        for step in self.steps:
            for tc in step.get("response", {}).get("tools_called", []):
                sig = f"{tc['name']}:{tc.get('input_summary', '')[:80]}"
                recent.append(sig)
                count = sum(1 for s in recent if s == sig)
                step_key = (step["step_id"], tc["name"])
                if count >= threshold and step_key not in seen_at_step:
                    seen_at_step[step_key] = True
                    anomalies.append({
                        "type": "REPETITION",
                        "step_id": step["step_id"],
                        "tool": tc["name"],
                        "count": count,
                        "severity": "HIGH" if count >= 5 else "MEDIUM",
                    })
        return anomalies

    def detect_error_spiral(self):
        """Detect increasing error sequences based on tool results failing."""
        anomalies = []
        consecutive_errors = 0
        spiral_start = None

        for step in self.steps:
            # Check tool results for errors (stop_reason, or error keywords in summary)
            stop = step.get("response", {}).get("stop_reason", "")
            summary = step.get("response", {}).get("text_summary", "").lower()

            # Only count as error if the agent is REACTING to an error
            # (mentions error/fail AND is re-reading or re-trying)
            tools = [tc["name"] for tc in step.get("response", {}).get("tools_called", [])]
            has_error_text = any(kw in summary for kw in ["error", "fail", "econnrefused", "cannot connect", "connection refused"])
            is_retry = any(kw in summary for kw in ["again", "re-read", "retry", "still", "persists", "didn't work", "another approach", "try once more"])

            has_error = (stop == "error") or (has_error_text and is_retry)

            if has_error:
                consecutive_errors += 1
                if consecutive_errors == 1:
                    spiral_start = step["step_id"]
                if consecutive_errors >= 3:
                    anomalies.append({
                        "type": "ERROR_SPIRAL",
                        "start_step": spiral_start,
                        "current_step": step["step_id"],
                        "consecutive_errors": consecutive_errors,
                        "severity": "CRITICAL" if consecutive_errors >= 5 else "HIGH",
                    })
            else:
                consecutive_errors = 0
                spiral_start = None
        return anomalies

    def _compute_tool_entropy(self):
        """Shannon entropy of tool usage distribution. Higher = more diverse."""
        import math
        counts: dict[str, int] = {}
        total = 0
        for step in self.steps:
            for tc in step.get("response", {}).get("tools_called", []):
                counts[tc["name"]] = counts.get(tc["name"], 0) + 1
                total += 1
        if total == 0 or len(counts) <= 1:
            return 0.0
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
        max_entropy = math.log2(len(counts)) if len(counts) > 1 else 1.0
        return entropy / max_entropy  # normalized 0-1

    def compute_health_score(self):
        """Weighted composite health score 0-100.
        Components:
          structural (0.4) — loops + repetition
          memory     (0.3) — context decay/rot
          stability  (0.2) — error spirals
          diversity  (0.1) — tool entropy
        """
        loops = self.detect_loops()
        context = self.detect_context_decay()
        repetition = self.detect_repetition()
        spirals = self.detect_error_spiral()

        # Structural: loops + repetition (0-100, 100 = no issues)
        loop_penalty = min(50, len(loops) * 15)
        rep_penalty = min(50, len(set(a["step_id"] for a in repetition)) * 6) if repetition else 0
        structural = max(0, 100 - loop_penalty - rep_penalty)

        # Memory: context decay/rot (0-100)
        critical_count = sum(1 for a in context if a["severity"] == "CRITICAL")
        high_count = sum(1 for a in context if a["severity"] == "HIGH")
        medium_count = sum(1 for a in context if a["severity"] == "MEDIUM")
        memory = max(0, 100 - critical_count * 15 - high_count * 8 - medium_count * 3)

        # Stability: error spirals (0-100)
        if spirals:
            max_consecutive = max(a["consecutive_errors"] for a in spirals)
            stability = max(0, 100 - max_consecutive * 12)
        else:
            stability = 100

        # Diversity: tool entropy (0-100)
        diversity = round(self._compute_tool_entropy() * 100)

        # Weighted composite
        score = round(
            structural * 0.4
            + memory * 0.3
            + stability * 0.2
            + diversity * 0.1
        )

        return max(0, min(100, score))

    def compute_health_breakdown(self):
        """Return per-component health scores for the dashboard."""
        loops = self.detect_loops()
        context = self.detect_context_decay()
        repetition = self.detect_repetition()
        spirals = self.detect_error_spiral()

        loop_penalty = min(50, len(loops) * 15)
        rep_penalty = min(50, len(set(a["step_id"] for a in repetition)) * 6) if repetition else 0
        structural = max(0, 100 - loop_penalty - rep_penalty)

        critical_count = sum(1 for a in context if a["severity"] == "CRITICAL")
        high_count = sum(1 for a in context if a["severity"] == "HIGH")
        medium_count = sum(1 for a in context if a["severity"] == "MEDIUM")
        memory = max(0, 100 - critical_count * 15 - high_count * 8 - medium_count * 3)

        if spirals:
            max_consecutive = max(a["consecutive_errors"] for a in spirals)
            stability = max(0, 100 - max_consecutive * 12)
        else:
            stability = 100

        diversity = round(self._compute_tool_entropy() * 100)

        return {
            "structural": {"score": structural, "weight": 0.4},
            "memory": {"score": memory, "weight": 0.3},
            "stability": {"score": stability, "weight": 0.2},
            "diversity": {"score": diversity, "weight": 0.1},
        }

    def find_degradation_point(self):
        """Find the first step where cumulative health drops below 70."""
        if len(self.steps) < 3:
            return None
        # Simulate running health up to each step
        for i in range(2, len(self.steps)):
            sub_analyzer = TrajectoryAnalyzer.__new__(TrajectoryAnalyzer)
            sub_analyzer.steps = self.steps[:i + 1]
            score = sub_analyzer.compute_health_score()
            if score < 70:
                return {
                    "step_id": self.steps[i]["step_id"],
                    "health_at_point": score,
                    "message": f"Health dropped to {score} at step {self.steps[i]['step_id']}",
                }
        return None

    def full_analysis(self):
        """Return complete analysis for the dashboard."""
        return {
            "total_steps": len(self.steps),
            "health_score": self.compute_health_score(),
            "health_breakdown": self.compute_health_breakdown(),
            "degradation_point": self.find_degradation_point(),
            "anomalies": {
                "loops": self.detect_loops(),
                "context_decay": self.detect_context_decay(),
                "repetition": self.detect_repetition(),
                "error_spirals": self.detect_error_spiral(),
            },
            "steps": self.steps,
            "summary": {
                "total_tokens": self.steps[-1]["trajectory_metrics"]["cumulative_tokens"] if self.steps else 0,
                "final_context_pct": self.steps[-1]["trajectory_metrics"]["context_utilization_pct"] if self.steps else 0,
                "total_tool_calls": sum(
                    len(s.get("response", {}).get("tools_called", [])) for s in self.steps
                ),
                "total_duration_s": sum(
                    s.get("trajectory_metrics", {}).get("step_duration_ms", 0) for s in self.steps
                ) / 1000,
            },
        }
