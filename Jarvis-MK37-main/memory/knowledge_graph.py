"""
Knowledge Graph — SQLite-backed entities/facts/relationships.

Sidecar du memory_manager JSON (coexiste, ne remplace pas).
- entities(id, name, type, created_at)
- facts(id, entity_id, key, value, source, confidence, updated_at)
- relationships(id, src_id, dst_id, type, weight, updated_at)

API haut-niveau : add_entity, add_fact, link, search, get_entity, get_related.
Fallback silencieux si sqlite3 indispo.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
DB_PATH  = BASE_DIR / "memory" / "knowledge_graph.db"
_lock    = Lock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL DEFAULT 'thing',
    created_at REAL NOT NULL,
    UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   INTEGER NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    source      TEXT DEFAULT 'user',
    confidence  REAL DEFAULT 1.0,
    updated_at  REAL NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE(entity_id, key)
);

CREATE TABLE IF NOT EXISTS relationships (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id      INTEGER NOT NULL,
    dst_id      INTEGER NOT NULL,
    type        TEXT NOT NULL,
    weight      REAL DEFAULT 1.0,
    updated_at  REAL NOT NULL,
    FOREIGN KEY(src_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY(dst_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE(src_id, dst_id, type)
);

CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity_id);
CREATE INDEX IF NOT EXISTS idx_rel_src ON relationships(src_id);
CREATE INDEX IF NOT EXISTS idx_rel_dst ON relationships(dst_id);
"""


class KnowledgeGraph:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        c = sqlite3.connect(str(self.db_path))
        c.execute("PRAGMA foreign_keys = ON")
        c.row_factory = sqlite3.Row
        return c

    # ---------- entities ----------

    def add_entity(self, name: str, type_: str = "thing") -> int:
        with _lock, self._conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO entities(name,type,created_at) VALUES(?,?,?)",
                (name, type_, time.time()),
            )
            if cur.lastrowid:
                return cur.lastrowid
            row = c.execute(
                "SELECT id FROM entities WHERE name=? AND type=?", (name, type_)
            ).fetchone()
            return row["id"]

    def get_entity(self, name: str, type_: Optional[str] = None) -> Optional[dict]:
        with _lock, self._conn() as c:
            if type_:
                row = c.execute(
                    "SELECT * FROM entities WHERE name=? AND type=?", (name, type_)
                ).fetchone()
            else:
                row = c.execute("SELECT * FROM entities WHERE name=?", (name,)).fetchone()
            return dict(row) if row else None

    # ---------- facts ----------

    def add_fact(
        self,
        entity_name: str,
        key: str,
        value: str,
        entity_type: str = "thing",
        source: str = "user",
        confidence: float = 1.0,
    ) -> int:
        eid = self.add_entity(entity_name, entity_type)
        with _lock, self._conn() as c:
            c.execute(
                """INSERT INTO facts(entity_id,key,value,source,confidence,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(entity_id,key) DO UPDATE SET
                     value=excluded.value,
                     source=excluded.source,
                     confidence=excluded.confidence,
                     updated_at=excluded.updated_at""",
                (eid, key, value, source, confidence, time.time()),
            )
            return eid

    def facts_of(self, entity_name: str, type_: Optional[str] = None) -> list[dict]:
        ent = self.get_entity(entity_name, type_)
        if not ent:
            return []
        with _lock, self._conn() as c:
            rows = c.execute(
                "SELECT key,value,source,confidence,updated_at FROM facts WHERE entity_id=? ORDER BY updated_at DESC",
                (ent["id"],),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------- relationships ----------

    def link(
        self, src_name: str, dst_name: str, type_: str,
        src_type: str = "thing", dst_type: str = "thing", weight: float = 1.0,
    ) -> None:
        src = self.add_entity(src_name, src_type)
        dst = self.add_entity(dst_name, dst_type)
        with _lock, self._conn() as c:
            c.execute(
                """INSERT INTO relationships(src_id,dst_id,type,weight,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(src_id,dst_id,type) DO UPDATE SET
                     weight=excluded.weight, updated_at=excluded.updated_at""",
                (src, dst, type_, weight, time.time()),
            )

    def related(self, name: str, type_: Optional[str] = None) -> list[dict]:
        ent = self.get_entity(name, type_)
        if not ent:
            return []
        with _lock, self._conn() as c:
            rows = c.execute(
                """SELECT e.name AS name, e.type AS type, r.type AS rel, r.weight AS weight
                   FROM relationships r
                   JOIN entities e ON e.id = r.dst_id
                   WHERE r.src_id=?
                   ORDER BY r.weight DESC""",
                (ent["id"],),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------- search ----------

    def search(self, query: str, limit: int = 20) -> list[dict]:
        q = f"%{query.lower()}%"
        with _lock, self._conn() as c:
            rows = c.execute(
                """SELECT e.name AS entity, e.type AS type, f.key, f.value
                   FROM facts f JOIN entities e ON e.id=f.entity_id
                   WHERE lower(f.value) LIKE ? OR lower(f.key) LIKE ? OR lower(e.name) LIKE ?
                   ORDER BY f.updated_at DESC LIMIT ?""",
                (q, q, q, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------- stats ----------

    def stats(self) -> dict:
        with _lock, self._conn() as c:
            e = c.execute("SELECT COUNT(*) n FROM entities").fetchone()["n"]
            f = c.execute("SELECT COUNT(*) n FROM facts").fetchone()["n"]
            r = c.execute("SELECT COUNT(*) n FROM relationships").fetchone()["n"]
            return {"entities": e, "facts": f, "relationships": r}


_KG_SINGLETON: Optional[KnowledgeGraph] = None


def get_kg() -> KnowledgeGraph:
    global _KG_SINGLETON
    if _KG_SINGLETON is None:
        _KG_SINGLETON = KnowledgeGraph()
    return _KG_SINGLETON
