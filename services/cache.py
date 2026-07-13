"""Simple in-memory TTL cache for activity summaries."""
import time
from collections import OrderedDict
from typing import Any, Optional


class TTLCache:
    """A simple TTL cache with max size eviction."""

    def __init__(self, max_size: int = 50, default_ttl: int = 120):
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl  # seconds

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        expires_at, value = self._cache[key]
        if time.monotonic() > expires_at:
            del self._cache[key]
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self.max_size:
            # Remove oldest (least recently used)
            self._cache.popitem(last=False)
        ttl = ttl if ttl is not None else self.default_ttl
        self._cache[key] = (time.monotonic() + ttl, value)

    def invalidate(self, key_prefix: str = ""):
        if not key_prefix:
            self._cache.clear()
            return
        keys_to_delete = [k for k in self._cache if k.startswith(key_prefix)]
        for k in keys_to_delete:
            del self._cache[k]

    def __len__(self) -> int:
        # Clean expired entries
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]
        return len(self._cache)


# Global cache instances
activity_cache = TTLCache(max_size=30, default_ttl=60)  # 1 min for activity data
summary_cache = TTLCache(max_size=20, default_ttl=300)  # 5 min for daily summaries
