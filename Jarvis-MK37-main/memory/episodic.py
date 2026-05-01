"""
Episodic memory — timeline persistante des événements importants.

Différent du working memory (volatile) et du semantic (facts):
ICI = "ce qui s'est passé, quand, et avec quel résultat".

Stockage : SQLite `memory/episodic.db` (table episodes).
  - id, timestamp, type, summary, details (JSON), emotional_valence (-1..1)
  - related_entities (text array de noms)

Indexable par date, type, mot-clé. Sert de base au RAG cross-couches.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
DB_PATH  = BASE_DIR / "memory" / "episodic.db"
_lock    = threading.RLock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         REAL    NOT NULL,
    type              TEXT    NOT NULL,
    summary           TEXT    NOT NULL,
    details_json      TEXT    DEFAULT '{}',
    emotional_valence REAL    DEFAULT 0.0,
    related_entities  TEXT    DEFAULT '',
    voice_used        INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ep_ts ON episodes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ep_type ON episodes(type);
"""


EPISODE_TYPES = {
    "conversation",   # tour user/assistant
    "tool_call",      # action exécutée
    "mission",        # mission async terminée
    "error",          # erreur runtime
    "preference",     # user a exprimé une préférence
    "discovery",      # info nouvelle apprise
    "milestone",      # événement marquant (fin de projet, etc.)
}


@dataclass
class Episode:
    timestamp:         float
    type:              str
    summary:           str
    details:           dict = field(default_factory=dict)
    emotional_valence: float = 0.0
    related_entities:  list[str] = field(default_factory=list)
    voice_used:        int = 0
    id:                Optional[int] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Episode":
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            type=row["type"],
            summary=row["summary"],
            details=json.loads(row["details_json"] or "{}"),
            emotional_valence=row["emotional_valence"],
            related_entities=(row["related_entities"] or "").split("|") if row["related_entities"] else [],
            voice_used=row["voice_used"],
        )

    def iso_time(self) -> str:
        return datetime.fromtimestamp(self.timestamp).isoformat(timespec="seconds")


class EpisodicMemory:

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def write(
        self,
        type_:             str,
        summary:           str,
        details:           Optional[dict] = None,
        emotional_valence: float = 0.0,
        related_entities:  Optional[list[str]] = None,
        voice_used:        int = 0,
    ) -> int:
        related = "|".join(related_entities or [])
        with _lock, self._conn() as c:
            cur = c.execute(
                """INSERT INTO episodes(timestamp,type,summary,details_json,
                       emotional_valence,related_entities,voice_used)
                   VALUES(?,?,?,?,?,?,?)""",
                (time.time(), type_, summary,
                 json.dumps(details or {}, ensure_ascii=False),
                 emotional_valence, related, voice_used),
            )
            return cur.lastrowid

    def recent(self, n: int = 20, type_: Optional[str] = None) -> list[Episode]:
        with _lock, self._conn() as c:
            if type_:
                rows = c.execute(
                    "SELECT * FROM episodes WHERE type=? ORDER BY timestamp DESC LIMIT ?",
                    (type_, n),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?", (n,)
                ).fetchall()
            return [Episode.from_row(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[Episode]:
        q = f"%{query.lower()}%"
        with _lock, self._conn() as c:
            rows = c.execute(
                """SELECT * FROM episodes
                   WHERE lower(summary) LIKE ? OR lower(details_json) LIKE ?
                      OR lower(related_entities) LIKE ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (q, q, q, limit),
            ).fetchall()
            return [Episode.from_row(r) for r in rows]

    def by_entity(self, entity_name: str, limit: int = 20) -> list[Episode]:
        with _lock, self._conn() as c:
            rows = c.execute(
                """SELECT * FROM episodes
                   WHERE related_entities LIKE ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (f"%{entity_name}%", limit),
            ).fetchall()
            return [Episode.from_row(r) for r in rows]

    def stats(self) -> dict:
        with _lock, self._conn() as c:
            n = c.execute("SELECT COUNT(*) AS n FROM episodes").fetchone()["n"]
            by_type = {}
            for row in c.execute("SELECT type, COUNT(*) AS n FROM episodes GROUP BY type"):
                by_type[row["type"]] = row["n"]
            return {"total": n, "by_type": by_type}

    def clear_older_than(self, cutoff_timestamp: float) -> int:
        """Supprime les épisodes plus vieux que cutoff. Retourne le nombre supprimé."""
        with _lock, self._conn() as c:
            cur = c.execute("DELETE FROM episodes WHERE timestamp < ?", (cutoff_timestamp,))
            return cur.rowcount


_EM_SINGLETON: Optional[EpisodicMemory] = None


def get_episodic() -> EpisodicMemory:
    global _EM_SINGLETON
    if _EM_SINGLETON is None:
        _EM_SINGLETON = EpisodicMemory()
    return _EM_SINGLETON


def reset_episodic() -> None:
    global _EM_SINGLETON
    _EM_SINGLETON = None
