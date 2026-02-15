#!/usr/bin/env python3
"""Interactive CLI for the in-memory KV store."""

import shlex

from db import KVStore


HELP = """
Commands:
  set <key> <value>        Store a value
  get <key>                Retrieve a value
  del <key>                Delete a key
  ttl <key> <seconds>      Set expiry on a key
  remaining <key>          Show remaining TTL
  keys                     List all live keys
  flush                    Clear the entire store
  help                     Show this message
  exit / quit              Quit
"""


def run_command(db: KVStore, line: str) -> bool:
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        print(f"Parse error: {exc}")
        return True

    if not parts:
        return True

    cmd, *args = parts
    cmd = cmd.lower()

    if cmd in ("exit", "quit"):
        return False

    elif cmd == "help":
        print(HELP)

    elif cmd == "set":
        if len(args) != 2:
            print("Usage: set <key> <value>")
        else:
            db.set(args[0], args[1])
            print("OK")

    elif cmd == "get":
        if len(args) != 1:
            print("Usage: get <key>")
        else:
            val = db.get(args[0])
            print(repr(val) if val is not None else "(nil)")

    elif cmd == "del":
        if len(args) != 1:
            print("Usage: del <key>")
        else:
            print("OK" if db.delete(args[0]) else "(key not found)")

    elif cmd == "ttl":
        if len(args) != 2:
            print("Usage: ttl <key> <seconds>")
        else:
            try:
                secs = float(args[1])
            except ValueError:
                print("seconds must be a number")
                return True
            print("OK" if db.ttl(args[0], secs) else "(key not found)")

    elif cmd == "remaining":
        if len(args) != 1:
            print("Usage: remaining <key>")
        else:
            r = db.remaining_ttl(args[0])
            if r == -1.0:
                print("(key not found or expired)")
            elif r is None:
                print("(no expiry)")
            else:
                print(f"{r:.3f}s")

    elif cmd == "keys":
        live = db.keys()
        print(live if live else "(empty)")

    elif cmd == "flush":
        db.flush()
        print("OK")

    else:
        print(f"Unknown command '{cmd}'. Type 'help' for usage.")

    return True


def main() -> None:
    db = KVStore()
    print("KV Store CLI — type 'help' for commands, 'exit' to quit.")
    try:
        while True:
            try:
                line = input("kv> ").strip()
            except EOFError:
                break
            if not run_command(db, line):
                break
    finally:
        db.stop()
    print("Bye.")


if __name__ == "__main__":
    main()
