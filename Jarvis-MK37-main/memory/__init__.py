"""Memory system — 4-layer unified API with RAG retrieval.

4 couches:
  - working: volatile (20 tours FIFO)
  - episodic: timeline des événements (persistent SQLite)
  - semantic: facts stables (persistent JSON)
  - procedural: recettes apprises (persistent JSON)

RAG: retrieval cross-couches avec embeddings sentence-transformers.

Usage:
    from memory import get_memory
    
    mem = get_memory()
    
    # Working memory (volatile)
    mem.add_turn("user", "Quel est ton nom?", intent="identity")
    ctx = mem.get_working_context(last_n=10)
    
    # Episodic (events timeline)
    mem.write_episode("conversation", "User asked about name")
    recent = mem.get_recent_episodes(n=10)
    
    # Semantic (facts)
    mem.update_fact("name", "Claude", category="identity")
    fact = mem.get_fact("name")
    
    # Procedural (recipes)
    mem.add_procedure(
        name="export_pdf",
        description="Export document to PDF",
        steps=["File > Export", "Select PDF format", "Save"],
        triggers=["export", "pdf"]
    )
    
    # RAG retrieval
    results = mem.retrieve("Quel est mon nom?", k=5)
    context = mem.get_retrieval_context("Quel est mon nom?")
    
    # Maintenance
    mem.decay_old_episodes(days_threshold=30)
    mem.flush_caches()
    
    # Stats
    stats = mem.stats()
"""

from memory.memory_manager import (
    get_memory,
    reset_memory,
    load_memory,
    save_memory,
    update_memory,
    format_memory_for_prompt,
    MemoryManager,
)

from memory.working_memory import get_working_memory, WorkingMemory
from memory.episodic import get_episodic, EpisodicMemory
from memory.semantic import get_semantic_memory, SemanticMemory
from memory.procedural import get_procedural, ProceduralMemory
from memory.rag import get_rag, RAG

__all__ = [
    # Main API
    "get_memory",
    "MemoryManager",
    
    # Backward compat
    "load_memory",
    "save_memory",
    "update_memory",
    "format_memory_for_prompt",
    "reset_memory",
    
    # Layer accessors
    "get_working_memory",
    "get_episodic",
    "get_semantic_memory",
    "get_procedural",
    "get_rag",
]
