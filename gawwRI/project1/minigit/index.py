"""Staging area (index) manager.

The index is a JSON file at ``.minigit/index``:
    { "relative/path/to/file.txt": "<sha1>", ... }
"""
import json
import os


class IndexManager:
    def __init__(self, minigit_path: str) -> None:
        self._path = os.path.join(minigit_path, "index")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def read(self) -> dict:
        """Return the full index dict from disk (empty dict if no index yet)."""
        if not os.path.exists(self._path):
            return {}
        with open(self._path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return json.loads(content) if content else {}

    def write(self, entries: dict) -> None:
        """Overwrite the on-disk index with *entries*."""
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(self, filename: str, blob_hash: str) -> None:
        """Stage *filename* at *blob_hash*, overwriting any previous entry."""
        entries = self.read()
        entries[filename] = blob_hash
        self.write(entries)

    def remove(self, filename: str) -> bool:
        """Unstage *filename*. Returns True if it was staged."""
        entries = self.read()
        if filename not in entries:
            return False
        del entries[filename]
        self.write(entries)
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_entries(self) -> dict:
        """Return a snapshot of all staged ``{filename: blob_hash}`` pairs."""
        return self.read()
