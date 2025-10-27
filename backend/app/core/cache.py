"""Simple cache manager used by media rendering.

Provides an in-memory TTL cache with optional pluggable backend later.
This is intentionally lightweight to keep tests stable.
"""

import time
from threading import RLock
from typing import Any


class CacheEntry:
    def __init__(self, value: Any, expires_at: float):
        self.value = value
        self.expires_at = expires_at


class CacheManager:
    """Very small in-memory cache manager with TTL support.

    Methods:
    - get(key) -> Optional[value]
    - set(key, value, ttl)
    - delete(key)
    """

    def __init__(self):
        self._store: dict[str, CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry.expires_at < now:
                # expired
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if ttl is None:
            ttl = 3600
        expires_at = time.time() + ttl
        with self._lock:
            self._store[key] = CacheEntry(value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            if key in self._store:
                del self._store[key]


# Convenience singleton used by application code
_GLOBAL_CACHE: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = CacheManager()
    return _GLOBAL_CACHE
