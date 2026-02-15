"""
Interactive CLI for the in-memory KV database.

Usage:
    python cli.py

Commands (case-insensitive):
    SET  <key> <value>
    GET  <key>
    DEL  <key>
    TTL  <key> <seconds>
    RTTL <key>          -- show remaining TTL
    KEYS                -- list all keys
    FLUSH               -- remove all keys
    HELP                -- show this help
    EXIT / QUIT         -- exit
"""

import shlex
import sys

from db import KVDatabase


HELP_TEXT = __doc__


def run_repl(db: KVDatabase) -> None:
    print("KV-DB CLI  (type HELP for commands, EXIT to quit)")
    while True:
        try:
            raw = input("kv> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            continue

        cmd, *args = parts
        cmd = cmd.upper()

        if cmd in ("EXIT", "QUIT"):
            break

        elif cmd == "HELP":
            print(HELP_TEXT)

        elif cmd == "SET":
            if len(args) < 2:
                print("Usage: SET <key> <value>")
                continue
            key, value = args[0], " ".join(args[1:])
            db.set(key, value)
            print("OK")

        elif cmd == "GET":
            if len(args) != 1:
                print("Usage: GET <key>")
                continue
            val = db.get(args[0])
            print(repr(val) if val is not None else "(nil)")

        elif cmd == "DEL":
            if len(args) != 1:
                print("Usage: DEL <key>")
                continue
            removed = db.delete(args[0])
            print("(1)" if removed else "(0)")

        elif cmd == "TTL":
            if len(args) != 2:
                print("Usage: TTL <key> <seconds>")
                continue
            try:
                seconds = float(args[1])
            except ValueError:
                print("seconds must be a number")
                continue
            ok = db.ttl(args[0], seconds)
            print("OK" if ok else "(key not found)")

        elif cmd == "RTTL":
            if len(args) != 1:
                print("Usage: RTTL <key>")
                continue
            remaining = db.remaining_ttl(args[0])
            if remaining is None:
                print("(no TTL)")
            elif remaining < 0:
                print("(key not found or expired)")
            else:
                print(f"{remaining:.3f}s remaining")

        elif cmd == "KEYS":
            keys = db.keys()
            if keys:
                print("\n".join(keys))
            else:
                print("(empty)")

        elif cmd == "FLUSH":
            db.flush()
            print("OK")

        else:
            print(f"Unknown command: {cmd!r}  (type HELP for commands)")

    db.close()
    print("Bye.")


if __name__ == "__main__":
    run_repl(KVDatabase())
