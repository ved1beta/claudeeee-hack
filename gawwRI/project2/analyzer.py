"""
Static code analyzer for Python projects.

Detects:
  - Unused imports (imported names never referenced in the module body)
  - Functions longer than N lines (default: 20)

Output: JSON report written to stdout (or a file with -o).

Usage:
    python analyzer.py <path> [--max-lines N] [-o report.json]
    python analyzer.py project/         # scan a directory
    python analyzer.py single_file.py   # scan one file
"""

import ast
import json
import os
import sys
import argparse
from typing import Any


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

class _NameCollector(ast.NodeVisitor):
    """Collect every Name / Attribute used in an AST subtree."""

    def __init__(self):
        self.used: set[str] = set()

    def visit_Name(self, node: ast.Name):
        self.used.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # collect the root name of a.b.c → "a"
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name):
            self.used.add(root.id)
        self.generic_visit(node)


def _collect_imports(tree: ast.Module) -> list[dict[str, Any]]:
    """
    Return a list of imported *local* names together with source location.
    Each entry: {"name": str, "module": str, "line": int}
    """
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname if alias.asname else alias.name.split(".")[0]
                imports.append({"name": local_name, "module": alias.name, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue  # star imports can't be statically checked
                local_name = alias.asname if alias.asname else alias.name
                imports.append({"name": local_name, "module": f"{module}.{alias.name}", "line": node.lineno})
    return imports


def _collect_used_names(tree: ast.Module) -> set[str]:
    """Return all names actually *used* in the module (outside import statements)."""
    collector = _NameCollector()
    for node in ast.walk(tree):
        # skip the import statements themselves
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        collector.visit(node)
    return collector.used


def _find_long_functions(tree: ast.Module, max_lines: int) -> list[dict[str, Any]]:
    """
    Return functions/methods whose body spans more than max_lines source lines.
    Counts only the body lines (end_lineno - lineno, excluding the def line itself).
    """
    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.end_lineno is not None:
                length = node.end_lineno - node.lineno  # body lines
                if length > max_lines:
                    results.append({
                        "name": node.name,
                        "line_start": node.lineno,
                        "line_end": node.end_lineno,
                        "body_lines": length,
                    })
    return results


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

def analyze_file(path: str, max_lines: int) -> dict[str, Any]:
    """
    Parse *path* and return an analysis dict.
    On parse error returns a dict with an "error" key instead.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        return {"file": path, "error": str(exc)}

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return {"file": path, "error": f"SyntaxError: {exc}"}

    imports = _collect_imports(tree)
    used_names = _collect_used_names(tree)

    unused_imports = [
        imp for imp in imports if imp["name"] not in used_names
    ]

    long_functions = _find_long_functions(tree, max_lines)

    return {
        "file": path,
        "unused_imports": unused_imports,
        "long_functions": long_functions,
    }


# ---------------------------------------------------------------------------
# Directory walk
# ---------------------------------------------------------------------------

def collect_python_files(root: str) -> list[str]:
    """Recursively collect all .py files under *root*."""
    py_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden / venv / __pycache__ directories
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in ("__pycache__", "venv", ".venv", "env", "node_modules")
        ]
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(os.path.join(dirpath, fname))
    return sorted(py_files)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(target: str, max_lines: int) -> dict[str, Any]:
    if os.path.isfile(target):
        files = [target]
    elif os.path.isdir(target):
        files = collect_python_files(target)
    else:
        return {"error": f"Path not found: {target}", "results": []}

    results = [analyze_file(f, max_lines) for f in files]

    total_unused = sum(len(r.get("unused_imports", [])) for r in results)
    total_long = sum(len(r.get("long_functions", [])) for r in results)

    return {
        "summary": {
            "files_scanned": len(files),
            "total_unused_imports": total_unused,
            "total_long_functions": total_long,
            "max_function_lines": max_lines,
        },
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Static analyzer: unused imports + long functions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("target", help="Python file or directory to analyze")
    parser.add_argument(
        "--max-lines", type=int, default=20,
        metavar="N",
        help="Flag functions with more than N body lines (default: 20)",
    )
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="Write JSON report to FILE instead of stdout",
    )
    parser.add_argument(
        "--indent", type=int, default=2,
        help="JSON indentation level (default: 2)",
    )

    args = parser.parse_args()
    report = build_report(args.target, args.max_lines)
    output = json.dumps(report, indent=args.indent)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
