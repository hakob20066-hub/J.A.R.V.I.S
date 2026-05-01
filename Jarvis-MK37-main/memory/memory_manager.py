"""
Memory manager — API unifiée pour les 4 couches de mémoire.

Structure :
  - working: volatile RAM (20 tours FIFO)
  - episodic: événements timeline (persistent SQLite)
  - semantic: facts stables (persistent JSON)
  - procedural: recettes apprises (persistent JSON)

RAG automatique : retrieve(query) combine les 4 couches avec embeddings.

Décroissance :
  - Episodic : >30 jours → digest mensuel
  - Working : FIFO auto (>20 → drop oldest)
  - Semantic : aucune (facts permanents)
  - Procedural : aucune (recettes stables)

API publique :
  mem = get_memory()
  mem.write_episode(event_type, summary, details)
  mem.update_fact(key, value, category="knowledge")
  mem.add_procedure(name, description, steps, triggers)
  results = mem.retrieve(query, k=5)
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import sys

# Import des sous-couches
from .working_memory import get_working_memory, WorkingMemory
from .episodic import get_episodic, EpisodicMemory, Episode
from .semantic import get_semantic_memory, SemanticMemory, SemanticFact
from .procedural import get_procedural, ProceduralMemory, Procedure
from .rag import get_rag, RAG, RetrievalResult


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
_memory_lock = threading.RLock()


def _truncate_value(val: str, max_len: int = 380) -> str:
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len].rstrip() + "…"
    return val


class MemoryManager:
    """API unifiée pour les 4 couches de mémoire + RAG."""

    def __init__(self):
        self.working = get_working_memory()
        self.episodic = get_episodic()
        self.semantic = get_semantic_memory()
        self.procedural = get_procedural()
        self.rag = get_rag()
        self._lock = threading.RLock()

    # ========== WORKING MEMORY ==========

    def add_turn(self, role: str, content: str, **metadata) -> None:
        """Ajoute un tour à la working memory (volatile)."""
        self.working.add_turn(role, content, **metadata)

    def get_working_context(self, last_n: int = 10) -> str:
        """Récupère les N derniers tours formatés."""
        return self.working.format_for_prompt(n=last_n)

    def clear_working_memory(self) -> None:
        """Vide la working memory."""
        self.working.clear()

    # ========== EPISODIC MEMORY ==========

    def write_episode(
        self,
        event_type: str,
        summary: str,
        details: Optional[dict] = None,
        emotional_valence: float = 0.0,
        entities: Optional[list[str]] = None,
    ) -> int:
        """Écrit un événement episodique."""
        return self.episodic.write(
            type_=event_type,
            summary=summary,
            details=details,
            emotional_valence=emotional_valence,
            related_entities=entities,
        )

    def get_recent_episodes(self, n: int = 20, event_type: Optional[str] = None) -> list[Episode]:
        """Récupère les N derniers événements."""
        return self.episodic.recent(n=n, type_=event_type)

    def search_episodes(self, query: str, limit: int = 10) -> list[Episode]:
        """Recherche dans les événements."""
        return self.episodic.search(query, limit=limit)

    def get_episodes_by_entity(self, entity: str, limit: int = 20) -> list[Episode]:
        """Récupère tous les épisodes mentionnant une entité."""
        return self.episodic.by_entity(entity, limit=limit)

    # ========== SEMANTIC MEMORY ==========

    def update_fact(
        self,
        key: str,
        value: str,
        category: str = "knowledge",
        confidence: float = 1.0,
    ) -> SemanticFact:
        """Ajoute ou met à jour un fact sémantique."""
        return self.semantic.add_fact(
            key=key,
            value=value,
            category=category,
            confidence=confidence,
        )

    def get_fact(self, key: str) -> Optional[SemanticFact]:
        """Récupère un fact par clé."""
        return self.semantic.get_fact(key)

    def get_facts_by_category(self, category: str) -> list[SemanticFact]:
        """Récupère tous les facts d'une catégorie."""
        return self.semantic.get_by_category(category)

    def delete_fact(self, key: str) -> bool:
        """Supprime un fact."""
        return self.semantic.delete_fact(key)

    # ========== PROCEDURAL MEMORY ==========

    def add_procedure(
        self,
        name: str,
        description: str,
        steps: list[str],
        triggers: Optional[list[str]] = None,
    ) -> Procedure:
        """Ajoute une recette apprendre."""
        proc = Procedure(
            name=name,
            description=description,
            steps=steps,
            triggers=triggers or [],
        )
        self.procedural.add(proc)
        return proc

    def get_procedure(self, name: str) -> Optional[Procedure]:
        """Récupère une recette par nom."""
        return self.procedural.get(name)

    def find_procedures_by_trigger(self, query: str) -> list[Procedure]:
        """Trouvé des recettes par mot-clé trigger."""
        return self.procedural.find_by_trigger(query)

    def record_procedure_success(self, name: str) -> None:
        """Enregistre succès d'une recette."""
        self.procedural.record_success(name)

    def record_procedure_failure(self, name: str) -> None:
        """Enregistre échec d'une recette."""
        self.procedural.record_failure(name)

    # ========== RAG RETRIEVAL ==========

    def retrieve(
        self,
        query: str,
        k: int = 5,
        include_working: bool = True,
        include_episodic: bool = True,
        include_semantic: bool = True,
        include_procedural: bool = True,
    ) -> list[RetrievalResult]:
        """
        Retrieval cross-couches RAG automatique.
        
        Args:
            query: texte de requête
            k: nombre de résultats max
            include_*: filtrer les couches à inclure
        
        Returns:
            liste des top-k résultats pondérés par pertinence + récence
        """
        with self._lock:
            return self.rag.retrieve(
                query=query,
                working_memory=self.working if include_working else None,
                episodic_memory=self.episodic if include_episodic else None,
                semantic_memory=self.semantic if include_semantic else None,
                procedural_memory=self.procedural if include_procedural else None,
                k=k,
            )

    def get_retrieval_context(
        self,
        query: str,
        k: int = 5,
        separator: str = "\n---\n",
    ) -> str:
        """Format les résultats RAG en contexte texte pour LLM."""
        results = self.retrieve(query, k=k)
        if not results:
            return ""
        
        lines = [f"[Retrieved context for: {query}]"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n[{i}. {r.source.upper()} - score {r.score:.2f}]")
            lines.append(r.text)
        
        return separator.join(lines)

    # ========== DÉCROISSANCE & MAINTENANCE ==========

    def decay_old_episodes(self, days_threshold: int = 30) -> int:
        """
        Archive/supprime les épisodes > days_threshold.
        Retourne le nombre supprimé.
        """
        cutoff = time.time() - (days_threshold * 86400)
        removed = self.episodic.clear_older_than(cutoff)
        if removed > 0:
            print(f"[Memory] CLEANUP: Removed {removed} old episodes (>{days_threshold} days)")
        return removed

    def flush_caches(self) -> None:
        """Force save de tous les caches."""
        self.rag.cache.flush()

    # ========== STATS & EXPORT ==========

    def stats(self) -> dict:
        """Retourne stats sur les 4 couches."""
        return {
            "working": {
                "size": self.working.size(),
                "max": self.working.max_turns,
            },
            "episodic": self.episodic.stats(),
            "semantic": {
                "facts": len(self.semantic.all_facts()),
            },
            "procedural": self.procedural.stats(),
        }

    def export_all(self) -> dict:
        """Exporte toutes les mémoires en dict."""
        return {
            "working": self.working.to_dicts(),
            "episodic": [asdict(ep) for ep in self.episodic.recent(n=1000)],
            "semantic": self.semantic.to_dict(),
            "procedural": {
                n: p.to_dict() for n, p in 
                [(p.name, p) for p in self.procedural.list_all()]
            },
        }

    def format_for_prompt(self) -> str:
        """Formate les infos essentielles pour injection LLM."""
        lines = []
        
        # Identité (semantic)
        identity = self.semantic.get_by_category("identity")
        if identity:
            lines.append("=== IDENTITY ===")
            for fact in identity[:5]:
                lines.append(f"{fact.key}: {fact.value}")
        
        # Préférences (semantic)
        prefs = self.semantic.get_by_category("preference")
        if prefs:
            lines.append("\n=== PREFERENCES ===")
            for fact in prefs[:5]:
                lines.append(f"- {fact.value}")
        
        # Récents episodes (episodic)
        recent = self.episodic.recent(n=3)
        if recent:
            lines.append("\n=== RECENT EVENTS ===")
            for ep in recent:
                lines.append(f"[{ep.type}] {ep.summary}")
        
        # Working memory
        wm_ctx = self.get_working_context(last_n=5)
        if wm_ctx:
            lines.append("\n=== RECENT TURNS ===")
            lines.append(wm_ctx)
        
        return "\n".join(lines)


# ========== BACKWARD COMPATIBILITY ==========

def load_memory() -> dict:
    """Load old format (backward compat)."""
    mgr = get_memory()
    return mgr.export_all()


def save_memory(memory: dict) -> None:
    """Save (no-op in new system)."""
    pass


def update_memory(updates: dict) -> dict:
    """Update facts (backward compat)."""
    mgr = get_memory()
    if isinstance(updates, dict):
        for key, value in updates.items():
            if isinstance(value, dict) and "value" in value:
                mgr.update_fact(key, value["value"])
            else:
                mgr.update_fact(key, str(value))
    return load_memory()


def format_memory_for_prompt(memory: dict | None = None) -> str:
    """Format pour LLM (backward compat)."""
    mgr = get_memory()
    return mgr.format_for_prompt()


# ========== SINGLETON ==========

_memory_manager_instance: Optional[MemoryManager] = None
_memory_manager_lock = threading.RLock()


def get_memory() -> MemoryManager:
    """Retourne l'instance globale MemoryManager."""
    global _memory_manager_instance
    with _memory_manager_lock:
        if _memory_manager_instance is None:
            _memory_manager_instance = MemoryManager()
        return _memory_manager_instance


def reset_memory() -> None:
    """Réinitialise le manager (pour tests)."""
    global _memory_manager_instance
    _memory_manager_instance = None


# ========== IMPORT COMPATIBILITY ==========

# Garder les anciens accès en import direct
from dataclasses import asdict

