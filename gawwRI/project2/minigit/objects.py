"""
Content-addressable object store.

Object format (mirrors Git's loose object format):
    <type> <size>\x00<raw-data>

The whole thing is zlib-compressed and stored at:
    .minigit/objects/<hash[:2]>/<hash[2:]>

Three object types
------------------
blob   – raw file content
tree   – flat list of "mode name\x00blob_hash" entries (one per line)
commit – JSON document with tree/parent/message/author/timestamp
"""

import json
import os
import time

from utils import compress, decompress, read_file, sha1_hash, write_file


# ---------------------------------------------------------------------------
# Low-level object store
# ---------------------------------------------------------------------------

class ObjectStore:
    def __init__(self, git_dir: str):
        self.objects_dir = os.path.join(git_dir, "objects")
        os.makedirs(self.objects_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _object_path(self, hash_: str) -> str:
        return os.path.join(self.objects_dir, hash_[:2], hash_[2:])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_object(self, obj_type: str, data: bytes) -> str:
        """Hash, store (if new) and return the SHA-1 of the object."""
        header = f"{obj_type} {len(data)}\x00".encode()
        full = header + data
        hash_ = sha1_hash(full)
        path = self._object_path(hash_)
        if not os.path.exists(path):
            write_file(path, compress(full))
        return hash_

    def read_object(self, hash_: str) -> tuple:
        """Return (obj_type: str, data: bytes) for the given hash."""
        path = self._object_path(hash_)
        raw = decompress(read_file(path))
        null_idx = raw.index(b"\x00")
        header = raw[:null_idx].decode()
        obj_type, _ = header.split(" ", 1)
        return obj_type, raw[null_idx + 1:]

    def object_exists(self, hash_: str) -> bool:
        return os.path.exists(self._object_path(hash_))

    def resolve_prefix(self, prefix: str) -> str:
        """
        Expand a short (>=4 char) hash prefix to its full 40-char hash.
        Raises if not found or ambiguous.
        """
        if len(prefix) == 40:
            return prefix
        bucket = prefix[:2]
        rest = prefix[2:]
        bucket_dir = os.path.join(self.objects_dir, bucket)
        if not os.path.isdir(bucket_dir):
            raise KeyError(f"Object not found: {prefix}")
        matches = [
            bucket + name
            for name in os.listdir(bucket_dir)
            if name.startswith(rest)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise KeyError(f"Ambiguous short hash: {prefix}")
        raise KeyError(f"Object not found: {prefix}")


# ---------------------------------------------------------------------------
# High-level object helpers
# ---------------------------------------------------------------------------

class Blob:
    """Stores raw file content."""

    @staticmethod
    def create(store: ObjectStore, content: bytes) -> str:
        return store.write_object("blob", content)

    @staticmethod
    def read(store: ObjectStore, hash_: str) -> bytes:
        obj_type, data = store.read_object(hash_)
        if obj_type != "blob":
            raise TypeError(f"Expected blob, got {obj_type}")
        return data


class Tree:
    """
    Maps filename -> (mode, blob_hash).

    On-disk format (before zlib):
        100644 a.txt\x00<40-char-hash>\n100644 b.txt\x00<hash>...
    """

    @staticmethod
    def create(store: ObjectStore, entries: dict) -> str:
        """
        entries: {filename: (mode_str, blob_hash), ...}
        Returns the tree hash.
        """
        parts = []
        for name in sorted(entries):
            mode, blob_hash = entries[name]
            parts.append(f"{mode} {name}\x00{blob_hash}")
        raw = "\n".join(parts).encode()
        return store.write_object("tree", raw)

    @staticmethod
    def read(store: ObjectStore, hash_: str) -> dict:
        """Returns {filename: (mode, blob_hash), ...}"""
        obj_type, data = store.read_object(hash_)
        if obj_type != "tree":
            raise TypeError(f"Expected tree, got {obj_type}")
        entries = {}
        if not data:
            return entries
        for line in data.decode().split("\n"):
            if not line:
                continue
            null_idx = line.index("\x00")
            mode, name = line[:null_idx].split(" ", 1)
            blob_hash = line[null_idx + 1:]
            entries[name] = (mode, blob_hash)
        return entries


class Commit:
    """
    Stores commit metadata as JSON.

    Fields: tree, parent, message, author, timestamp
    """

    @staticmethod
    def create(
        store: ObjectStore,
        tree_hash: str,
        parent_hash: str,
        message: str,
        author: str = "Unknown",
    ) -> str:
        payload = {
            "tree": tree_hash,
            "parent": parent_hash,      # empty string means no parent
            "message": message,
            "author": author,
            "timestamp": time.time(),
        }
        raw = json.dumps(payload, indent=2).encode()
        return store.write_object("commit", raw)

    @staticmethod
    def read(store: ObjectStore, hash_: str) -> dict:
        obj_type, data = store.read_object(hash_)
        if obj_type != "commit":
            raise TypeError(f"Expected commit, got {obj_type}")
        return json.loads(data.decode())
