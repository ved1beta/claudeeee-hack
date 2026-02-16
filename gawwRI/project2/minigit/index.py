"""
Staging area (index).

Stored as a JSON file: .minigit/index
Schema: {"filepath": "blob_hash", ...}
"""

import json
import os


class Index:
    def __init__(self, git_dir: str):
        self._path = os.path.join(git_dir, "index")
        self._entries: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if os.path.exists(self._path):
            with open(self._path, "r") as f:
                self._entries = json.load(f)
        else:
            self._entries = {}

    def _save(self):
        with open(self._path, "w") as f:
            json.dump(self._entries, f, indent=2)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(self, filepath: str, blob_hash: str):
        """Stage a file (add or update)."""
        self._entries[filepath] = blob_hash
        self._save()

    def remove(self, filepath: str):
        """Unstage a file."""
        if filepath in self._entries:
            del self._entries[filepath]
            self._save()

    def clear(self):
        """Remove all staged entries (called after a commit)."""
        self._entries = {}
        self._save()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_entries(self) -> dict:
        """Return a copy of {filepath: blob_hash}."""
        return dict(self._entries)

    def is_staged(self, filepath: str) -> bool:
        return filepath in self._entries

    def get_hash(self, filepath: str) -> str | None:
        return self._entries.get(filepath)
