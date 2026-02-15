import threading
import time
from typing import Any, Optional


class KVStore:
    def __init__(self, cleanup_interval: float = 1.0):
        self._store: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}
        self._lock = threading.RLock()

        self._stop_event = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            args=(cleanup_interval,),
            daemon=True,
        )
        self._cleanup_thread.start()

    # --- Public API ---

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value
            self._expiry.pop(key, None)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if self._is_expired(key):
                self._evict(key)
                return None
            return self._store.get(key)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key not in self._store:
                return False
            self._evict(key)
            return True

    def ttl(self, key: str, seconds: float) -> bool:
        """Set expiry on an existing key. Returns False if key doesn't exist."""
        with self._lock:
            if key not in self._store:
                return False
            self._expiry[key] = time.monotonic() + seconds
            return True

    def remaining_ttl(self, key: str) -> Optional[float]:
        """Return seconds until expiry, None if no TTL, -1 if key missing/expired."""
        with self._lock:
            if key not in self._store or self._is_expired(key):
                return -1.0
            if key not in self._expiry:
                return None
            return max(0.0, self._expiry[key] - time.monotonic())

    def keys(self) -> list[str]:
        with self._lock:
            return [k for k in self._store if not self._is_expired(k)]

    def flush(self) -> None:
        with self._lock:
            self._store.clear()
            self._expiry.clear()

    def stop(self) -> None:
        """Stop the background cleanup thread."""
        self._stop_event.set()

    # --- Internal helpers ---

    def _is_expired(self, key: str) -> bool:
        deadline = self._expiry.get(key)
        return deadline is not None and time.monotonic() >= deadline

    def _evict(self, key: str) -> None:
        self._store.pop(key, None)
        self._expiry.pop(key, None)

    def _cleanup_loop(self, interval: float) -> None:
        while not self._stop_event.wait(interval):
            with self._lock:
                expired = [k for k in list(self._expiry) if self._is_expired(k)]
                for key in expired:
                    self._evict(key)
