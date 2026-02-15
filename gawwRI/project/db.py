"""
In-memory key-value store with TTL support and automatic expiry cleanup.
"""

import threading
import time
from typing import Any, Optional


class KVDatabase:
    def __init__(self, cleanup_interval: float = 1.0):
        self._store: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}  # key -> expiry timestamp
        self._lock = threading.RLock()

        # Background cleanup thread
        self._stop_event = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            args=(cleanup_interval,),
            daemon=True,
        )
        self._cleanup_thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Store key with value. Clears any existing TTL for the key."""
        with self._lock:
            self._store[key] = value
            self._expiry.pop(key, None)

    def get(self, key: str) -> Optional[Any]:
        """Return value for key, or None if missing / expired."""
        with self._lock:
            if self._is_expired(key):
                self._evict(key)
                return None
            return self._store.get(key)

    def delete(self, key: str) -> bool:
        """Remove key. Returns True if key existed, False otherwise."""
        with self._lock:
            existed = key in self._store
            self._evict(key)
            return existed

    def ttl(self, key: str, seconds: float) -> bool:
        """
        Set expiry of *seconds* from now on an existing key.
        Returns True on success, False if key does not exist.
        """
        with self._lock:
            if key not in self._store or self._is_expired(key):
                return False
            self._expiry[key] = time.monotonic() + seconds
            return True

    def remaining_ttl(self, key: str) -> Optional[float]:
        """
        Return seconds remaining until expiry, None if no TTL is set,
        or -1 if the key does not exist / is already expired.
        """
        with self._lock:
            if key not in self._store:
                return -1.0
            if key not in self._expiry:
                return None
            remaining = self._expiry[key] - time.monotonic()
            if remaining <= 0:
                self._evict(key)
                return -1.0
            return remaining

    def keys(self) -> list[str]:
        """Return all live (non-expired) keys."""
        with self._lock:
            self._purge_expired()
            return list(self._store.keys())

    def flush(self) -> None:
        """Remove all keys and TTLs."""
        with self._lock:
            self._store.clear()
            self._expiry.clear()

    def close(self) -> None:
        """Stop the background cleanup thread."""
        self._stop_event.set()
        self._cleanup_thread.join(timeout=2)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, key: str) -> bool:
        exp = self._expiry.get(key)
        return exp is not None and time.monotonic() >= exp

    def _evict(self, key: str) -> None:
        self._store.pop(key, None)
        self._expiry.pop(key, None)

    def _purge_expired(self) -> None:
        expired = [k for k in list(self._expiry) if self._is_expired(k)]
        for key in expired:
            self._evict(key)

    def _cleanup_loop(self, interval: float) -> None:
        while not self._stop_event.wait(timeout=interval):
            with self._lock:
                self._purge_expired()

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.keys())

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __repr__(self) -> str:
        return f"KVDatabase(keys={self.keys()})"
