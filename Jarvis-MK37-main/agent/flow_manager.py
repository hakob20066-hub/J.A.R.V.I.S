"""
FlowManager — orchestration foreground/background des flux cognitifs.

Règles:
  - HIGH : requête utilisateur (foreground, contrôle, interruption)
  - LOW  : mission lourde (background, non bloquante)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


PRIORITY_HIGH = "high"
PRIORITY_LOW = "low"


@dataclass
class FlowTask:
    task_id: str
    description: str
    priority: str
    status: str = "running"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class FlowManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._high_requests: int = 0
        self._low_tasks: dict[str, FlowTask] = {}

    def register_high_request(self, description: str) -> None:
        with self._lock:
            self._high_requests += 1
            print(f"🟢[FAST] Foreground request #{self._high_requests}: {description[:80]}")

    def register_low_task(self, task_id: str, description: str) -> None:
        with self._lock:
            self._low_tasks[task_id] = FlowTask(
                task_id=task_id,
                description=description,
                priority=PRIORITY_LOW,
            )
            print(f"🟣[MISSION] Background task registered: {task_id[:8]}")

    def mark_low_task_done(self, task_id: str, status: str = "done") -> None:
        with self._lock:
            task = self._low_tasks.get(task_id)
            if task is None:
                return
            task.status = status
            task.updated_at = time.time()
            print(f"🟣[MISSION] Background task finished: {task_id[:8]} ({status})")

    def has_active_low_priority(self) -> bool:
        with self._lock:
            return any(t.status == "running" for t in self._low_tasks.values())

    def active_low_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._low_tasks.values() if t.status == "running")

    def get_task(self, task_id: str) -> Optional[FlowTask]:
        with self._lock:
            return self._low_tasks.get(task_id)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "high_requests": self._high_requests,
                "active_low": self.active_low_count(),
                "low_tasks": {
                    tid: {
                        "description": t.description,
                        "status": t.status,
                        "priority": t.priority,
                    }
                    for tid, t in self._low_tasks.items()
                },
            }


_FLOW_MANAGER_SINGLETON: Optional[FlowManager] = None
_FLOW_MANAGER_LOCK = threading.RLock()


def get_flow_manager() -> FlowManager:
    global _FLOW_MANAGER_SINGLETON
    with _FLOW_MANAGER_LOCK:
        if _FLOW_MANAGER_SINGLETON is None:
            _FLOW_MANAGER_SINGLETON = FlowManager()
        return _FLOW_MANAGER_SINGLETON


def reset_flow_manager() -> None:
    global _FLOW_MANAGER_SINGLETON
    with _FLOW_MANAGER_LOCK:
        _FLOW_MANAGER_SINGLETON = None
