"""TokenBucket rate limiter — par connecteur."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class TokenBucket:
    capacity: float          # tokens max
    refill_rate: float       # tokens/seconde
    tokens: float = 0.0
    last_refill: float = 0.0

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.time()

    def consume(self, n: float = 1.0) -> bool:
        """Tente de consommer n tokens. False si pas assez."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


class RateLimiter:
    """Buckets nommés (1 par connecteur). Thread-safe."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.RLock()

    def configure(self, name: str, requests_per_hour: int) -> None:
        rate = requests_per_hour / 3600.0
        with self._lock:
            self._buckets[name] = TokenBucket(capacity=requests_per_hour, refill_rate=rate)

    def acquire(self, name: str) -> bool:
        with self._lock:
            bucket = self._buckets.get(name)
            if bucket is None:
                return True  # pas configuré = illimité
            return bucket.consume(1.0)

    def status(self) -> dict:
        with self._lock:
            return {n: round(b.tokens, 2) for n, b in self._buckets.items()}


_LIMITER_SINGLETON = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _LIMITER_SINGLETON
