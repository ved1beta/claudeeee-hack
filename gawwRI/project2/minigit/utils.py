import hashlib
import os
import zlib


def sha1_hash(data: bytes) -> str:
    """Return hex SHA-1 digest of bytes."""
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


def compress(data: bytes) -> bytes:
    return zlib.compress(data)


def decompress(data: bytes) -> bytes:
    return zlib.decompress(data)
