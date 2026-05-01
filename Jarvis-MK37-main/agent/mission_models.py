"""
Mission models — Voie 3 (async background tasks).

Mission = unité de travail long-terme (peut prendre minutes/heures/jours).
Persistence dans memory/missions.json via mission_store.MissionStore.

Status flow:
  pending  → running  → done
                     ↘ failed (retryable selon error_type)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional


VALID_STATUSES = {"pending", "running", "done", "failed", "cancelled"}


@dataclass
class Mission:
    id:           str                            # UUID
    description:  str                            # texte original de l'utilisateur
    status:       str = "pending"                # voir VALID_STATUSES
    created_at:   str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    started_at:   Optional[str] = None
    completed_at: Optional[str] = None
    result:       Optional[str] = None           # output final (pour mission top-level)
    error:        Optional[str] = None
    progress:     float = 0.0                    # 0.0 à 1.0
    parent_id:    Optional[str] = None           # si sub-mission d'une autre
    subtask_ids:  list[str] = field(default_factory=list)
    voice_used:   int = 3                        # 3 par défaut, peut être 2 ou 4 pour sub-tasks
    specialists_called: list[str] = field(default_factory=list)
    retry_count:  int = 0
    max_retries:  int = 2
    metadata:     dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Mission":
        # Tolérance aux clés manquantes (forward compat)
        valid_keys = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)

    def is_terminal(self) -> bool:
        return self.status in ("done", "failed", "cancelled")

    def can_retry(self) -> bool:
        return self.status == "failed" and self.retry_count < self.max_retries

    def mark_running(self) -> None:
        self.status = "running"
        self.started_at = datetime.now().isoformat(timespec="seconds")

    def mark_done(self, result: str) -> None:
        self.status = "done"
        self.completed_at = datetime.now().isoformat(timespec="seconds")
        self.result = result
        self.progress = 1.0

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.completed_at = datetime.now().isoformat(timespec="seconds")
        self.error = error
        self.retry_count += 1
