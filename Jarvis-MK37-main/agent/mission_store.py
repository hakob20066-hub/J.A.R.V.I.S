"""
MissionStore — persistence JSON pour les missions.

Stockage : memory/missions.json (configurable via path constructor).
Thread-safe (lock interne).

API :
  store.add(mission)
  store.get(mission_id)
  store.update(mission)
  store.get_pending() / get_running() / get_done()
  store.list_all()
  store.recover_orphans()  # missions "running" au démarrage → pending

Idempotency : add() ignore si l'id existe déjà (sauf si force=True).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from agent.mission_models import Mission


DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent / "memory" / "missions.json"


class MissionStore:

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        self._lock = threading.RLock()
        self._cache: dict[str, Mission] = {}
        self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if not self.path.exists():
            self._cache = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._cache = {
                mid: Mission.from_dict(m) for mid, m in data.items()
            }
        except Exception as e:
            print(f"[MissionStore] ⚠️ load failed: {e}")
            self._cache = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {mid: m.to_dict() for mid, m in self._cache.items()}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # ---------- CRUD ----------

    def add(self, mission: Mission, force: bool = False) -> bool:
        """Retourne True si ajouté, False si l'ID existait déjà."""
        with self._lock:
            if mission.id in self._cache and not force:
                return False
            self._cache[mission.id] = mission
            self._save()
            return True

    def get(self, mission_id: str) -> Optional[Mission]:
        with self._lock:
            return self._cache.get(mission_id)

    def update(self, mission: Mission) -> None:
        with self._lock:
            self._cache[mission.id] = mission
            self._save()

    def remove(self, mission_id: str) -> bool:
        with self._lock:
            if mission_id in self._cache:
                del self._cache[mission_id]
                self._save()
                return True
            return False

    # ---------- queries ----------

    def list_all(self) -> list[Mission]:
        with self._lock:
            return list(self._cache.values())

    def get_pending(self) -> list[Mission]:
        return self._by_status("pending")

    def get_running(self) -> list[Mission]:
        return self._by_status("running")

    def get_done(self) -> list[Mission]:
        return self._by_status("done")

    def get_failed_retryable(self) -> list[Mission]:
        with self._lock:
            return [m for m in self._cache.values() if m.can_retry()]

    def _by_status(self, status: str) -> list[Mission]:
        with self._lock:
            return [m for m in self._cache.values() if m.status == status]

    # ---------- claim / recovery ----------

    def claim_next_pending(self) -> Optional[Mission]:
        """
        Atomic : trouve la mission pending la plus ancienne, la marque running,
        et la retourne. Empêche 2 workers de traiter la même.
        """
        with self._lock:
            pending = sorted(self.get_pending(), key=lambda m: m.created_at)
            if not pending:
                return None
            m = pending[0]
            m.mark_running()
            self._save()
            return m

    def recover_orphans(self) -> list[Mission]:
        """
        Au démarrage : missions "running" = workers tués → reset à pending.
        Retourne la liste des récupérées.
        """
        with self._lock:
            recovered = []
            for m in self._cache.values():
                if m.status == "running":
                    m.status = "pending"
                    m.metadata["recovered_at"] = datetime.now().isoformat(timespec="seconds")
                    recovered.append(m)
            if recovered:
                self._save()
            return recovered

    # ---------- bulk ----------

    def stats(self) -> dict:
        with self._lock:
            counts = {s: 0 for s in ("pending", "running", "done", "failed", "cancelled")}
            for m in self._cache.values():
                counts[m.status] = counts.get(m.status, 0) + 1
            counts["total"] = len(self._cache)
            return counts

    def clear_done(self, keep_last: int = 50) -> int:
        """Supprime les missions done en gardant les `keep_last` plus récentes."""
        with self._lock:
            done = sorted(
                [m for m in self._cache.values() if m.status == "done"],
                key=lambda m: m.completed_at or "",
                reverse=True,
            )
            to_delete = done[keep_last:]
            for m in to_delete:
                del self._cache[m.id]
            if to_delete:
                self._save()
            return len(to_delete)
