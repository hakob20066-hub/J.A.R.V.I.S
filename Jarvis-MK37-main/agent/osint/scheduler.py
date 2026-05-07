"""
AdaptiveScheduler — pool asyncio dynamique selon CPU/RAM.

Voir [[14-Phases/phase7.6-scheduler-adaptive]].
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Awaitable, Callable, Optional

try:
    import psutil
    PSUTIL = True
except ImportError:
    PSUTIL = False


class AdaptiveScheduler:
    """
    Worker pool asyncio dont la taille s'ajuste selon CPU/RAM.
    Min 2, max cap 20. Probe toutes les 5s.
    """

    def __init__(
        self,
        min_workers: int = 2,
        max_workers_cap: int = 20,
        cpu_high_threshold: float = 80.0,
        ram_low_threshold_gb: float = 1.0,
        probe_interval: float = 5.0,
    ):
        self.min_workers = min_workers
        self.max_workers_cap = max_workers_cap
        self.cpu_high_threshold = cpu_high_threshold
        self.ram_low_threshold_gb = ram_low_threshold_gb
        self.probe_interval = probe_interval

        cores = os.cpu_count() or 4
        self.current_workers = max(min_workers, cores // 2)

        self._sem = asyncio.Semaphore(self.current_workers)
        self._inflight: int = 0
        self._completed: int = 0
        self._last_probe: float = 0.0
        self._last_cpu_high_since: Optional[float] = None
        self._last_ram_low_since:  Optional[float] = None
        self._lock = asyncio.Lock()

    async def submit(self, coro: Awaitable) -> any:
        """Acquire un slot, run la coro, release."""
        async with self._sem:
            self._inflight += 1
            try:
                self._maybe_probe()
                return await coro
            finally:
                self._inflight -= 1
                self._completed += 1

    async def map(self, coros: list[Awaitable]) -> list:
        """Run en parallèle avec limit du pool."""
        return await asyncio.gather(
            *[self.submit(c) for c in coros],
            return_exceptions=True,
        )

    def _maybe_probe(self) -> None:
        now = time.time()
        if now - self._last_probe < self.probe_interval:
            return
        self._last_probe = now
        if not PSUTIL:
            return  # pas d'ajustement sans psutil

        cpu = psutil.cpu_percent(interval=None)
        ram_avail_gb = psutil.virtual_memory().available / (1024 ** 3)

        # Sustained CPU high → réduire
        if cpu > self.cpu_high_threshold:
            self._last_cpu_high_since = self._last_cpu_high_since or now
            if now - self._last_cpu_high_since > self.probe_interval:
                self._shrink()
        else:
            self._last_cpu_high_since = None

        # Low RAM → réduire
        if ram_avail_gb < self.ram_low_threshold_gb:
            self._last_ram_low_since = self._last_ram_low_since or now
            if now - self._last_ram_low_since > self.probe_interval:
                self._shrink()
        else:
            self._last_ram_low_since = None

        # Tout ok et queue saturée → augmenter
        if cpu < 50 and ram_avail_gb > 2 * self.ram_low_threshold_gb \
                and self._inflight >= self.current_workers:
            self._grow()

    def _shrink(self) -> None:
        if self.current_workers <= self.min_workers:
            return
        self.current_workers -= 1
        # Recreate semaphore avec moins de tokens (best-effort)
        # Note: les inflight courants finissent normalement ; les nouveaux attendent.
        self._sem = asyncio.Semaphore(self.current_workers)

    def _grow(self) -> None:
        if self.current_workers >= self.max_workers_cap:
            return
        self.current_workers += 1
        self._sem = asyncio.Semaphore(self.current_workers)

    def status(self) -> dict:
        return {
            "current_workers": self.current_workers,
            "inflight":        self._inflight,
            "completed":       self._completed,
            "psutil":          PSUTIL,
        }
