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


DEFAULT_STORE_PATH   = Path(__file__).resolve().parent.parent / "memory" / "missions.json"
DEFAULT_ARCHIVE_PATH = Path(__file__).resolve().parent.parent / "memory" / "missions_archive.json"


class MissionStore:

    def __init__(self, path: Optional[Path] = None, archive_path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        # Archive séparée — missions done de sessions précédentes (queryable, non visible)
        if archive_path is not None:
            self.archive_path = Path(archive_path)
        elif path is not None:
            # Test isolation : archive à côté du store custom
            self.archive_path = Path(path).with_name("missions_archive.json")
        else:
            self.archive_path = DEFAULT_ARCHIVE_PATH
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
        Au démarrage :
          1. Missions "running" ou "pending" → cancelled (no auto-replay)
          2. Missions "done", "failed", "cancelled" → déplacées vers l'archive
             (visibles uniquement via query_archive(), pas dans la Task Queue UI)

        Le store en mémoire ne garde QUE les missions de la session courante.
        Retourne la liste des missions abandonnées (pour log).
        """
        with self._lock:
            abandoned = []
            archived_ids = []
            now = datetime.now().isoformat(timespec="seconds")

            for m in list(self._cache.values()):
                if m.status in ("running", "pending"):
                    m.status = "cancelled"
                    m.error = "abandoned at boot (previous session terminated)"
                    m.metadata["abandoned_at"] = now
                    abandoned.append(m)

            # Archive toutes les missions terminales (done/failed/cancelled)
            terminal = [m for m in self._cache.values()
                        if m.status in ("done", "failed", "cancelled")]
            if terminal:
                self._append_archive(terminal)
                for m in terminal:
                    archived_ids.append(m.id)
                    del self._cache[m.id]

            if abandoned or archived_ids:
                self._save()
            return abandoned

    # ---------- archive ----------

    def _append_archive(self, missions: list[Mission]) -> None:
        """Ajoute des missions au fichier d'archive."""
        try:
            self.archive_path.parent.mkdir(parents=True, exist_ok=True)
            existing: dict = {}
            if self.archive_path.exists():
                try:
                    existing = json.loads(self.archive_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            for m in missions:
                existing[m.id] = m.to_dict()
            tmp = self.archive_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.archive_path)
        except Exception as e:
            print(f"[MissionStore] ⚠️ archive failed: {e}")

    def query_archive(
        self,
        keyword: Optional[str] = None,
        limit: int = 20,
    ) -> list[Mission]:
        """
        Retourne les missions archivées (sessions précédentes).
        Filtre optionnel par mot-clé sur la description.
        Triées par date décroissante (plus récentes en premier).
        """
        if not self.archive_path.exists():
            return []
        try:
            data = json.loads(self.archive_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        missions = [Mission.from_dict(m) for m in data.values()]
        if keyword:
            kw = keyword.lower()
            missions = [m for m in missions if kw in (m.description or "").lower()]
        missions.sort(
            key=lambda m: m.completed_at or m.created_at or "",
            reverse=True,
        )
        return missions[:limit]

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
