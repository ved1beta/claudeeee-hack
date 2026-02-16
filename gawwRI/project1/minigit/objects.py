"""Content-addressable object storage.

Object types
------------
blob   : raw file bytes
tree   : text lines  ``blob <hash> <filename>``
commit : text lines  ``tree/parent/timestamp/message``
"""
import os
from utils import sha1_hash, read_file, write_file


# ---------------------------------------------------------------------------
# Low-level store
# ---------------------------------------------------------------------------

def object_path(minigit_path: str, hash_: str) -> str:
    """Return disk path for an object, split at 2 chars like real Git."""
    return os.path.join(minigit_path, "objects", hash_[:2], hash_[2:])


def write_object(minigit_path: str, data: bytes) -> str:
    """Persist *data* and return its SHA-1 hash (content-addressable)."""
    hash_ = sha1_hash(data)
    path = object_path(minigit_path, hash_)
    if not os.path.exists(path):
        write_file(path, data)
    return hash_


def read_object(minigit_path: str, hash_: str) -> bytes:
    """Return raw bytes for object *hash_*."""
    return read_file(object_path(minigit_path, hash_))


# ---------------------------------------------------------------------------
# Tree objects  {filename -> blob_hash}
# ---------------------------------------------------------------------------

def write_tree(minigit_path: str, entries: dict) -> str:
    """Serialise *entries* dict and store as a tree object."""
    lines = [f"blob {blob_hash} {filename}"
             for filename, blob_hash in sorted(entries.items())]
    return write_object(minigit_path, "\n".join(lines).encode())


def read_tree(minigit_path: str, tree_hash: str) -> dict:
    """Deserialise a tree object into ``{filename: blob_hash}``."""
    raw = read_object(minigit_path, tree_hash).decode()
    entries: dict = {}
    for line in raw.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3:
            _, blob_hash, filename = parts
            entries[filename] = blob_hash
    return entries


# ---------------------------------------------------------------------------
# Commit objects
# ---------------------------------------------------------------------------

def write_commit(
    minigit_path: str,
    tree_hash: str,
    parent_hash: str | None,
    message: str,
    timestamp: float,
) -> str:
    """Create and store a commit object; return its hash."""
    lines = [f"tree {tree_hash}"]
    if parent_hash:
        lines.append(f"parent {parent_hash}")
    lines.append(f"timestamp {timestamp}")
    lines.append(f"message {message}")
    return write_object(minigit_path, "\n".join(lines).encode())


def read_commit(minigit_path: str, commit_hash: str) -> dict:
    """Parse a commit object into a plain dict."""
    raw = read_object(minigit_path, commit_hash).decode()
    result: dict = {"hash": commit_hash, "parent": None}
    for line in raw.splitlines():
        if line.startswith("tree "):
            result["tree"] = line[5:]
        elif line.startswith("parent "):
            result["parent"] = line[7:]
        elif line.startswith("timestamp "):
            result["timestamp"] = float(line[10:])
        elif line.startswith("message "):
            result["message"] = line[8:]
    return result
