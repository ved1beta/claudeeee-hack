#!/usr/bin/env python3
"""
Static code analyzer — detects:
  - Unused imports
  - Functions longer than N lines

Usage:
  python analyzer.py [directory] [--max-lines N] [--output report.json]
"""

import ast
import argparse
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Visitors
# ---------------------------------------------------------------------------

class _NameCollector(ast.NodeVisitor):
    """Collect all Name and Attribute nodes used in an expression context."""

    def __init__(self):
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name):
        self.names.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Capture the root of dotted access  (e.g. os.path → "os")
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name):
            self.names.add(root.id)
        self.generic_visit(node)


def _collect_used_names(tree: ast.AST) -> set[str]:
    collector = _NameCollector()
    collector.visit(tree)
    return collector.names


def _analyze_file(path: Path, max_lines: int) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return {
            "path": str(path),
            "error": f"SyntaxError: {exc}",
            "unused_imports": [],
            "long_functions": [],
        }

    lines = source.splitlines()
    used_names = _collect_used_names(tree)

    # --- Unused imports ---
    unused_imports: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname if alias.asname else alias.name.split(".")[0]
                if bound_name not in used_names:
                    unused_imports.append({
                        "line": node.lineno,
                        "statement": f"import {alias.name}"
                        + (f" as {alias.asname}" if alias.asname else ""),
                        "bound_name": bound_name,
                    })

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound_name = alias.asname if alias.asname else alias.name
                if bound_name not in used_names:
                    unused_imports.append({
                        "line": node.lineno,
                        "statement": f"from {module} import {alias.name}"
                        + (f" as {alias.asname}" if alias.asname else ""),
                        "bound_name": bound_name,
                    })

    # --- Long functions ---
    long_functions: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno
        end = node.end_lineno or start
        length = end - start + 1
        if length > max_lines:
            long_functions.append({
                "name": node.name,
                "start_line": start,
                "end_line": end,
                "line_count": length,
            })

    return {
        "path": str(path),
        "unused_imports": unused_imports,
        "long_functions": long_functions,
    }


# ---------------------------------------------------------------------------
# Directory scan
# ---------------------------------------------------------------------------

def analyze_directory(root: str | Path, max_lines: int) -> list[dict]:
    root = Path(root)
    results = []
    for py_file in sorted(root.rglob("*.py")):
        result = _analyze_file(py_file, max_lines)
        # Only include files that have findings (or errors)
        if result.get("error") or result["unused_imports"] or result["long_functions"]:
            results.append(result)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Python static code analyzer")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=50,
        metavar="N",
        help="Flag functions longer than N lines (default: 50)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON report to FILE (default: print to stdout)",
    )
    args = parser.parse_args()

    findings = analyze_directory(args.directory, args.max_lines)

    report = {
        "scanned_directory": str(Path(args.directory).resolve()),
        "max_function_lines": args.max_lines,
        "files_with_issues": len(findings),
        "findings": findings,
    }

    output = json.dumps(report, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
