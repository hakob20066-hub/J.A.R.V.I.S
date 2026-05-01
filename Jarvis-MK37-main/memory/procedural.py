"""
Procedural memory — recettes / how-to apprises au fil du temps.

Stocke les "façons de faire" : "Pour exporter un pdf, fais ABC".
Différent de semantic (facts statiques) et episodic (événements).

Stockage : JSON `config/procedures.json`.

Format :
{
  "procedures": {
    "<name>": {
      "description": "...",
      "steps": ["...", "..."],
      "triggers": ["mots", "qui", "déclenchent"],
      "success_count": int,
      "failure_count": int,
      "last_used": ISO,
      "last_modified": ISO
    }
  }
}
"""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
PATH     = BASE_DIR / "config" / "procedures.json"
_lock    = threading.RLock()


@dataclass
class Procedure:
    name:           str
    description:    str
    steps:          list[str] = field(default_factory=list)
    triggers:       list[str] = field(default_factory=list)
    success_count:  int = 0
    failure_count:  int = 0
    last_used:      Optional[str] = None
    last_modified:  str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Procedure":
        return cls(name=name, **{k: v for k, v in d.items() if k != "name"})

    def reliability(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5


class ProceduralMemory:

    def __init__(self, path: Path = PATH):
        self.path = Path(path)
        self._procedures: dict[str, Procedure] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._procedures = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            procs = data.get("procedures", {})
            self._procedures = {
                name: Procedure.from_dict(name, p) for name, p in procs.items()
            }
        except Exception as e:
            print(f"[Procedural] WARNING: load failed: {e}")
            self._procedures = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"procedures": {n: p.to_dict() for n, p in self._procedures.items()}}
        # to_dict inclut name : on le retire pour éviter duplication
        for p in data["procedures"].values():
            p.pop("name", None)
        with _lock:
            self.path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def add(self, procedure: Procedure) -> None:
        with _lock:
            procedure.last_modified = datetime.now().isoformat(timespec="seconds")
            self._procedures[procedure.name] = procedure
            self._save()

    def get(self, name: str) -> Optional[Procedure]:
        with _lock:
            return self._procedures.get(name)

    def remove(self, name: str) -> bool:
        with _lock:
            if name in self._procedures:
                del self._procedures[name]
                self._save()
                return True
            return False

    def find_by_trigger(self, query: str) -> list[Procedure]:
        """Retourne les procédures dont un trigger matche la query."""
        low = query.lower()
        with _lock:
            return [
                p for p in self._procedures.values()
                if any(t.lower() in low for t in p.triggers)
            ]

    def list_all(self) -> list[Procedure]:
        with _lock:
            return list(self._procedures.values())

    def record_success(self, name: str) -> None:
        with _lock:
            p = self._procedures.get(name)
            if p:
                p.success_count += 1
                p.last_used = datetime.now().isoformat(timespec="seconds")
                self._save()

    def record_failure(self, name: str) -> None:
        with _lock:
            p = self._procedures.get(name)
            if p:
                p.failure_count += 1
                p.last_used = datetime.now().isoformat(timespec="seconds")
                self._save()

    def stats(self) -> dict:
        with _lock:
            return {
                "count": len(self._procedures),
                "names": list(self._procedures.keys()),
            }


_PM_SINGLETON: Optional[ProceduralMemory] = None


def get_procedural() -> ProceduralMemory:
    global _PM_SINGLETON
    if _PM_SINGLETON is None:
        _PM_SINGLETON = ProceduralMemory()
    return _PM_SINGLETON


def reset_procedural() -> None:
    global _PM_SINGLETON
    _PM_SINGLETON = None
