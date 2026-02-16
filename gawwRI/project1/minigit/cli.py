#!/usr/bin/env python3
"""minigit — a mini Git-like version control system.

Usage:
  minigit init
  minigit add <file> [<file> ...]
  minigit commit -m <message>
  minigit log
  minigit status
  minigit checkout <commit>
"""
import os
import sys

# Allow running as  python cli.py  from anywhere
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from repository import Repository


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_init(args: list[str]) -> None:
    Repository.init()


def cmd_add(args: list[str]) -> None:
    if not args:
        print("Usage: minigit add <file> [<file> ...]")
        sys.exit(1)
    repo = Repository()
    for path in args:
        try:
            repo.add(path)
        except FileNotFoundError as exc:
            print(f"error: {exc}")
            sys.exit(1)


def cmd_commit(args: list[str]) -> None:
    if len(args) < 2 or args[0] != "-m":
        print("Usage: minigit commit -m <message>")
        sys.exit(1)
    message = " ".join(args[1:])
    repo = Repository()
    if repo.commit(message) is None:
        sys.exit(1)


def cmd_log(args: list[str]) -> None:
    Repository().log()


def cmd_status(args: list[str]) -> None:
    Repository().status()


def cmd_checkout(args: list[str]) -> None:
    if not args:
        print("Usage: minigit checkout <commit>")
        sys.exit(1)
    try:
        Repository().checkout(args[0])
    except Exception as exc:
        print(f"error: {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

COMMANDS = {
    "init": cmd_init,
    "add": cmd_add,
    "commit": cmd_commit,
    "log": cmd_log,
    "status": cmd_status,
    "checkout": cmd_checkout,
}


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    if command not in COMMANDS:
        print(f"minigit: '{command}' is not a minigit command")
        print("Available commands: " + ", ".join(COMMANDS))
        sys.exit(1)

    try:
        COMMANDS[command](args)
    except Exception as exc:
        print(f"error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
