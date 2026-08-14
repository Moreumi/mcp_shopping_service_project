"""Small thread-safe TTL cache for single-process demo acceleration."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
import time


class TTLCache:
    def __init__(self, ttl_seconds: int, max_entries: int = 256):
        self.ttl_seconds = max(1, ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._values: dict[object, tuple[float, object]] = {}
        self._lock = Lock()

    def get(self, key):
        now = time.monotonic()
        with self._lock:
            item = self._values.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._values.pop(key, None)
                return None
            return deepcopy(value)

    def set(self, key, value):
        with self._lock:
            if len(self._values) >= self.max_entries:
                oldest = min(self._values, key=lambda entry: self._values[entry][0])
                self._values.pop(oldest, None)
            self._values[key] = (time.monotonic() + self.ttl_seconds, deepcopy(value))

    def clear(self):
        with self._lock:
            self._values.clear()
