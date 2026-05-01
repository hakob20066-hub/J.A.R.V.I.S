"""
RAG (Retrieval-Augmented Generation) — retrieval cross-couches mémoire.

Combine les 4 couches (working, episodic, semantic, procedural) via embeddings.
Utilise sentence-transformers pour local embeddings (80 MB, pas API externe).

Cosine similarity pour ranking, top-k retrieval avec pondération par récence + pertinence.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
import sys

try:
    from sentence_transformers import SentenceTransformer, util
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("[RAG] WARNING: sentence-transformers not installed. Install with: pip install sentence-transformers")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
CACHE_PATH = BASE_DIR / "memory" / "embeddings_cache.json"
_lock = threading.RLock()

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class RetrievalResult:
    """Résultat du RAG retrieval."""
    text: str
    source: str  # "working", "episodic", "semantic", "procedural"
    score: float  # 0..1, pertinence + récence
    metadata: dict = None
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata or {},
            "timestamp": self.timestamp,
        }


class EmbeddingCache:
    """Cache persistant des embeddings pour éviter recalcul."""

    def __init__(self, cache_path: Path = CACHE_PATH):
        self.cache_path = cache_path
        self.data: dict = {}
        self._load()

    def _load(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            with _lock:
                content = self.cache_path.read_text(encoding="utf-8")
                self.data = json.loads(content)
        except Exception as e:
            print(f"[EmbeddingCache] WARNING: Load failed: {e}")

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            self.cache_path.write_text(
                json.dumps(self.data, ensure_ascii=False),
                encoding="utf-8",
            )

    def get(self, text: str) -> Optional[list]:
        """Récupère embedding en cache."""
        key = hash(text) % (2**31)
        key_str = str(key)
        with _lock:
            if key_str in self.data:
                return self.data[key_str]
        return None

    def set(self, text: str, embedding: list) -> None:
        """Cache un embedding."""
        key = hash(text) % (2**31)
        key_str = str(key)
        with _lock:
            self.data[key_str] = embedding
            if len(self.data) % 100 == 0:
                self._save()

    def flush(self) -> None:
        """Force save."""
        with _lock:
            self._save()


class RAG:
    """Retrieval-Augmented Generation across memory layers."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.model = None
        self.cache = EmbeddingCache()
        self._lock = threading.RLock()
        
        if EMBEDDINGS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name)
            except Exception as e:
                print(f"[RAG] WARNING: Failed to load model: {e}")

    def _embed(self, text: str) -> Optional[list]:
        """Génère embedding pour texte."""
        if not self.model:
            return None
        
        # Cherche en cache d'abord
        cached = self.cache.get(text)
        if cached:
            return cached
        
        try:
            with _lock:
                embedding = self.model.encode(text, convert_to_tensor=False).tolist()
                self.cache.set(text, embedding)
                return embedding
        except Exception as e:
            print(f"[RAG] WARNING: Embedding failed: {e}")
            return None

    def _cosine_similarity(self, emb1: list, emb2: list) -> float:
        """Cosine similarity simple."""
        if not emb1 or not emb2:
            return 0.0
        try:
            import numpy as np
            a, b = np.array(emb1), np.array(emb2)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        except:
            return 0.0

    def retrieve(
        self,
        query: str,
        working_memory=None,
        episodic_memory=None,
        semantic_memory=None,
        procedural_memory=None,
        k: int = 5,
    ) -> list[RetrievalResult]:
        """
        Retrieval cross-couches avec RAG.
        
        Pondération:
        - Récence (plus récent = score boost)
        - Pertinence (cosine similarity)
        - Source (les couches proches comme working ont priorité)
        """
        if not self.model:
            # Fallback sans embeddings : recherche textuelle simple
            return self._fallback_retrieve(
                query,
                working_memory,
                episodic_memory,
                semantic_memory,
                procedural_memory,
                k,
            )
        
        query_emb = self._embed(query)
        if not query_emb:
            return self._fallback_retrieve(
                query,
                working_memory,
                episodic_memory,
                semantic_memory,
                procedural_memory,
                k,
            )
        
        candidates: list[tuple[RetrievalResult, float]] = []
        now = time.time()
        
        # Working memory (RAM, très récent)
        if working_memory:
            for turn in working_memory.get_all():
                emb = self._embed(turn.content)
                if emb:
                    sim = self._cosine_similarity(query_emb, emb)
                    # Bonus récence pour working
                    age_minutes = (now - turn.timestamp) / 60
                    recency_boost = max(0, 1.0 - (age_minutes / 30))  # decay après 30 min
                    final_score = (sim * 0.7 + recency_boost * 0.3)
                    candidates.append((
                        RetrievalResult(
                            text=turn.content,
                            source="working",
                            score=final_score,
                            metadata=turn.metadata,
                            timestamp=turn.timestamp,
                        ),
                        final_score,
                    ))
        
        # Episodic memory (timeline)
        if episodic_memory:
            episodes = episodic_memory.search(query, limit=20)
            for ep in episodes:
                emb = self._embed(ep.summary)
                if emb:
                    sim = self._cosine_similarity(query_emb, emb)
                    # Bonus récence, moins que working
                    age_days = (now - ep.timestamp) / 86400
                    recency_boost = max(0, 1.0 - (age_days / 30))
                    final_score = (sim * 0.8 + recency_boost * 0.2)
                    candidates.append((
                        RetrievalResult(
                            text=ep.summary,
                            source="episodic",
                            score=final_score,
                            metadata={
                                "type": ep.type,
                                "valence": ep.emotional_valence,
                                "entities": ep.related_entities,
                            },
                            timestamp=ep.timestamp,
                        ),
                        final_score,
                    ))
        
        # Semantic memory (facts)
        if semantic_memory:
            facts = semantic_memory.search(query)
            for fact in facts:
                emb = self._embed(fact.value)
                if emb:
                    sim = self._cosine_similarity(query_emb, emb)
                    # Pas de récence pour facts (constants)
                    final_score = sim * fact.confidence
                    candidates.append((
                        RetrievalResult(
                            text=fact.value,
                            source="semantic",
                            score=final_score,
                            metadata={
                                "category": fact.category,
                                "key": fact.key,
                            },
                            timestamp=0,  # Pas de timestamp
                        ),
                        final_score,
                    ))
        
        # Procedural memory (recettes)
        if procedural_memory:
            procs = procedural_memory.find_by_trigger(query)
            for proc in procs:
                steps_text = " ".join(proc.steps)
                emb = self._embed(steps_text)
                if emb:
                    sim = self._cosine_similarity(query_emb, emb)
                    # Bonus si fiable
                    reliability = proc.reliability()
                    final_score = (sim * 0.7 + reliability * 0.3)
                    candidates.append((
                        RetrievalResult(
                            text=f"{proc.name}: {proc.description}",
                            source="procedural",
                            score=final_score,
                            metadata={
                                "name": proc.name,
                                "reliability": reliability,
                                "triggers": proc.triggers,
                            },
                            timestamp=0,
                        ),
                        final_score,
                    ))
        
        # Tri par score (décroissant) et take top-k
        candidates.sort(key=lambda x: x[1], reverse=True)
        results = [item[0] for item in candidates[:k]]
        
        # Normalise scores à [0, 1]
        if results:
            max_score = max(r.score for r in results)
            if max_score > 0:
                for r in results:
                    r.score = r.score / max_score
        
        return results

    def _fallback_retrieve(
        self,
        query: str,
        working_memory,
        episodic_memory,
        semantic_memory,
        procedural_memory,
        k: int,
    ) -> list[RetrievalResult]:
        """Fallback sans embeddings : recherche textuelle."""
        q = query.lower()
        results = []
        
        if working_memory:
            for turn in working_memory.get_all():
                if q in turn.content.lower():
                    results.append(RetrievalResult(
                        text=turn.content,
                        source="working",
                        score=0.5,
                        metadata=turn.metadata,
                        timestamp=turn.timestamp,
                    ))
        
        if episodic_memory:
            for ep in episodic_memory.search(query, limit=10):
                results.append(RetrievalResult(
                    text=ep.summary,
                    source="episodic",
                    score=0.5,
                    metadata={"type": ep.type},
                    timestamp=ep.timestamp,
                ))
        
        if semantic_memory:
            for fact in semantic_memory.search(query):
                results.append(RetrievalResult(
                    text=fact.value,
                    source="semantic",
                    score=0.5,
                    metadata={"category": fact.category},
                ))
        
        return results[:k]


# Singleton global
_rag_instance: Optional[RAG] = None
_rag_lock = threading.RLock()


def get_rag() -> RAG:
    """Retourne l'instance RAG globale."""
    global _rag_instance
    with _rag_lock:
        if _rag_instance is None:
            _rag_instance = RAG()
        return _rag_instance


def flush_embeddings_cache() -> None:
    """Force save du cache embeddings."""
    rag = get_rag()
    rag.cache.flush()
