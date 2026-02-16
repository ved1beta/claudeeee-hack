"""Utility helpers shared across minigit modules."""
import os
import hashlib

MINIGIT_DIR = ".minigit"


def find_repo_root(start_path: str = None) -> str | None:
    """Walk up from start_path looking for a .minigit directory."""
    path = os.path.abspath(start_path or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(path, MINIGIT_DIR)):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def get_minigit_path(repo_root: str) -> str:
    return os.path.join(repo_root, MINIGIT_DIR)


def sha1_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def write_file(path: str, data: bytes) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
