"""
UI Activity Tracker — file d'activité temps réel pour le panel Task Queue.

Rôle :
  - Capte chaque tool call (pending → running → completed/failed)
  - Capte les goals user + steps du planner
  - Ring buffer léger, thread-safe
  - Lu par ui._metrics_loop() et envoyé à window.jarvisSetTasks

Pas de dépendances. Pas de persistence.
"""

from __future__ import annotations
import threading
import time
import uuid
from collections import deque


class UITracker:
    MAX = 12  # items gardés (completed purgés après délai)
    KEEP_DONE_SEC = 8  # garder les completed/failed 8s pour feedback visuel

    def __init__(self):
        self._items: dict[str, dict] = {}
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

    # ---------- public ----------

    def start(self, label: str, kind: str = "tool") -> str:
        tid = uuid.uuid4().hex[:6]
        item = {
            "id":       tid,
            "goal":     label[:60],
            "status":   "running",
            "progress": 50,
            "kind":     kind,
            "ts":       time.time(),
            "done_ts":  0.0,
        }
        with self._lock:
            self._items[tid] = item
            self._order.append(tid)
            self._trim()
        return tid

    def pending(self, label: str, kind: str = "step") -> str:
        tid = uuid.uuid4().hex[:6]
        item = {
            "id":       tid,
            "goal":     label[:60],
            "status":   "pending",
            "progress": 5,
            "kind":     kind,
            "ts":       time.time(),
            "done_ts":  0.0,
        }
        with self._lock:
            self._items[tid] = item
            self._order.append(tid)
            self._trim()
        return tid

    def succeed(self, tid: str, label: str | None = None) -> None:
        with self._lock:
            it = self._items.get(tid)
            if not it:
                return
            it["status"] = "completed"
            it["progress"] = 100
            it["done_ts"] = time.time()
            if label:
                it["goal"] = label[:60]

    def fail(self, tid: str, reason: str = "") -> None:
        with self._lock:
            it = self._items.get(tid)
            if not it:
                return
            it["status"] = "failed"
            it["progress"] = 100
            it["done_ts"] = time.time()
            if reason:
                it["goal"] = (it["goal"] + " — " + reason)[:60]

    def run(self, tid: str) -> None:
        with self._lock:
            it = self._items.get(tid)
            if it:
                it["status"] = "running"
                it["progress"] = 55

    def snapshot(self) -> list[dict]:
        now = time.time()
        with self._lock:
            # purge completed/failed after KEEP_DONE_SEC
            dead = [
                tid for tid, it in self._items.items()
                if it["done_ts"] and (now - it["done_ts"]) > self.KEEP_DONE_SEC
            ]
            for tid in dead:
                self._items.pop(tid, None)
                try:
                    self._order.remove(tid)
                except ValueError:
                    pass
            # newest first
            return [self._items[tid] for tid in list(self._order)[::-1] if tid in self._items]

    # ---------- internal ----------

    def _trim(self):
        while len(self._order) > self.MAX:
            tid = self._order.popleft()
            self._items.pop(tid, None)


_TRACKER: UITracker | None = None


def get_tracker() -> UITracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = UITracker()
    return _TRACKER
