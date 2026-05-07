"""
Semantic memory — facts persistants, connaissances stables.

Contrairement à episodic (événements) et procedural (recettes),
semantic stocke des "vérités" : identité, préférences, faits sur le monde.

Basé sur long_term.json existant mais restructuré pour RAG.

Format :
{
  "facts": {
    "<key>": {
      "value": str,
      "category": str,  # "identity", "preference", "relationship", "knowledge"
      "confidence": 0..1,
      "created": ISO,
      "updated": ISO,
      "embedding": [float]  # pour RAG
    }
  }
}

Pas de décroissance (facts permanents).
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone


def _now_iso() -> str:
    """ISO timestamp UTC tz-aware (remplace datetime.utcnow déprécié)."""
    return datetime.now(timezone.utc).isoformat()
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
LONG_TERM_PATH = BASE_DIR / "memory" / "long_term.json"
_lock = threading.RLock()


@dataclass
class SemanticFact:
    """Un fait sémantique."""
    key: str
    value: str
    category: str  # identity, preference, relationship, knowledge
    confidence: float = 1.0
    created: str = ""
    updated: str = ""
    embedding: list = None  # [dim]

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.embedding and isinstance(self.embedding, list):
            d["embedding"] = self.embedding
        return d

    @staticmethod
    def from_dict(d: dict) -> SemanticFact:
        return SemanticFact(
            key=d.get("key", ""),
            value=d.get("value", ""),
            category=d.get("category", "knowledge"),
            confidence=d.get("confidence", 1.0),
            created=d.get("created", _now_iso()),
            updated=d.get("updated", _now_iso()),
            embedding=d.get("embedding"),
        )


class SemanticMemory:
    """Persistent semantic facts store."""

    def __init__(self):
        self.facts: dict[str, SemanticFact] = {}
        self._load()

    def _load(self) -> None:
        """Charge depuis long_term.json."""
        if not LONG_TERM_PATH.exists():
            return
        with _lock:
            try:
                data = json.loads(LONG_TERM_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Import depuis l'ancien format
                    for cat, items in data.items():
                        if isinstance(items, dict):
                            for key, entry in items.items():
                                if isinstance(entry, dict) and "value" in entry:
                                    fact_key = f"{cat}/{key}"
                                    self.facts[fact_key] = SemanticFact(
                                        key=fact_key,
                                        value=entry.get("value", ""),
                                        category=cat,
                                        created=entry.get("created", _now_iso()),
                                        updated=entry.get("updated", _now_iso()),
                                    )
            except Exception as e:
                print(f"[Semantic] WARNING: Load error: {e}")

    def _save(self) -> None:
        """Persiste en JSON."""
        LONG_TERM_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            data = {}
            for fact in self.facts.values():
                cat = fact.category
                if cat not in data:
                    data[cat] = {}
                # Réconcile old format
                short_key = fact.key.split("/")[-1]
                data[cat][short_key] = {
                    "value": fact.value,
                    "created": fact.created,
                    "updated": fact.updated,
                }
            LONG_TERM_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def add_fact(
        self,
        key: str,
        value: str,
        category: str = "knowledge",
        confidence: float = 1.0,
    ) -> SemanticFact:
        """Ajoute / remplace un fact."""
        with _lock:
            now = _now_iso()
            if key in self.facts:
                fact = self.facts[key]
                fact.value = value
                fact.updated = now
                fact.confidence = max(fact.confidence, confidence)
            else:
                fact = SemanticFact(
                    key=key,
                    value=value,
                    category=category,
                    confidence=confidence,
                    created=now,
                    updated=now,
                )
                self.facts[key] = fact
            self._save()
            return fact

    def get_fact(self, key: str) -> Optional[SemanticFact]:
        """Récupère un fact par clé."""
        with _lock:
            return self.facts.get(key)

    def get_by_category(self, category: str) -> list[SemanticFact]:
        """Récupère tous les facts d'une catégorie."""
        with _lock:
            return [f for f in self.facts.values() if f.category == category]

    def search(self, query: str) -> list[SemanticFact]:
        """Recherche simple par texte."""
        q = query.lower()
        with _lock:
            return [
                f for f in self.facts.values()
                if q in f.key.lower() or q in f.value.lower()
            ]

    def delete_fact(self, key: str) -> bool:
        """Supprime un fact."""
        with _lock:
            if key in self.facts:
                del self.facts[key]
                self._save()
                return True
            return False

    def all_facts(self) -> list[SemanticFact]:
        """Retourne tous les facts."""
        with _lock:
            return list(self.facts.values())

    def to_dict(self) -> dict:
        """Sérialise en dict."""
        with _lock:
            return {k: v.to_dict() for k, v in self.facts.items()}


# Singleton global
_semantic_memory_instance: Optional[SemanticMemory] = None
_semantic_memory_lock = threading.RLock()


def get_semantic_memory() -> SemanticMemory:
    """Retourne l'instance globale."""
    global _semantic_memory_instance
    with _semantic_memory_lock:
        if _semantic_memory_instance is None:
            _semantic_memory_instance = SemanticMemory()
        return _semantic_memory_instance
