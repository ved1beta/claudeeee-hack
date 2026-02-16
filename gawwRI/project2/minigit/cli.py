#!/usr/bin/env python3
"""
minigit – a mini Git-like version-control system.

Usage:
    minigit init
    minigit add <file> [<file> ...]
    minigit commit -m <message>
    minigit log
    minigit status
    minigit checkout <commit>
"""

import argparse
import sys
import os

# Allow running as  python cli.py  from anywhere inside the project.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from repository import Repository


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_init(args):
    Repository.init(".")


def cmd_add(args):
    repo = Repository.find()
    for filepath in args.files:
        repo.add(filepath)


def cmd_commit(args):
    repo = Repository.find()
    repo.commit(args.message)


def cmd_log(args):
    repo = Repository.find()
    repo.log()


def cmd_status(args):
    repo = Repository.find()
    repo.status()


def cmd_checkout(args):
    repo = Repository.find()
    repo.checkout(args.commit)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minigit",
        description="A simplified Git-like version control system.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # init
    p_init = sub.add_parser("init", help="Initialise a new repository")
    p_init.set_defaults(func=cmd_init)

    # add
    p_add = sub.add_parser("add", help="Stage file(s) for the next commit")
    p_add.add_argument("files", nargs="+", metavar="<file>")
    p_add.set_defaults(func=cmd_add)

    # commit
    p_commit = sub.add_parser("commit", help="Record staged changes")
    p_commit.add_argument("-m", "--message", required=True, metavar="<msg>",
                          help="Commit message")
    p_commit.set_defaults(func=cmd_commit)

    # log
    p_log = sub.add_parser("log", help="Show commit history")
    p_log.set_defaults(func=cmd_log)

    # status
    p_status = sub.add_parser("status", help="Show working-tree status")
    p_status.set_defaults(func=cmd_status)

    # checkout
    p_checkout = sub.add_parser("checkout", help="Restore working tree to a commit")
    p_checkout.add_argument("commit", metavar="<commit>",
                            help="Full or abbreviated commit hash")
    p_checkout.set_defaults(func=cmd_checkout)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (FileNotFoundError, FileExistsError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
