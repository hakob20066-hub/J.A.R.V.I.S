"""
Test d'intégration du système de mémoire 4 couches + RAG.

Tests:
  1. Working memory (FIFO)
  2. Episodic memory (events)
  3. Semantic memory (facts)
  4. Procedural memory (recipes)
  5. RAG retrieval
  6. Backward compatibility
"""

import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory import (
    get_memory,
    reset_memory,
)


def test_working_memory():
    """Test working memory (volatile FIFO)."""
    print("\n=== Test Working Memory ===")
    mem = get_memory()
    
    # Add turns
    for i in range(25):
        mem.add_turn("user", f"Message {i}", intent="test")
    
    size = mem.working.size()
    print(f"[OK] Added 25 turns, size = {size} (max should be 20)")
    assert size == 20, f"Expected 20, got {size}"
    
    # Get context
    ctx = mem.get_working_context(last_n=5)
    print(f"[OK] Last 5 turns context retrieved")
    
    return True


def test_episodic_memory():
    """Test episodic memory (events timeline)."""
    print("\n=== Test Episodic Memory ===")
    mem = get_memory()
    
    # Write episodes
    ep1 = mem.write_episode(
        "conversation",
        "User asked about memory system",
        details={"topic": "memory"},
        entities=["user", "memory"]
    )
    print(f"[OK] Wrote episode {ep1}")
    
    ep2 = mem.write_episode(
        "discovery",
        "Learned about RAG retrieval",
        details={"tech": "RAG"},
        emotional_valence=0.8,
        entities=["RAG", "retrieval"]
    )
    print(f"[OK] Wrote episode {ep2}")
    
    # Search
    results = mem.search_episodes("memory", limit=5)
    print(f"[OK] Found {len(results)} episodes about 'memory'")
    
    # Get by entity
    by_entity = mem.get_episodes_by_entity("memory", limit=10)
    print(f"[OK] Found {len(by_entity)} episodes mentioning 'memory'")
    
    return True


def test_semantic_memory():
    """Test semantic memory (persistent facts)."""
    print("\n=== Test Semantic Memory ===")
    mem = get_memory()
    
    # Add facts
    mem.update_fact("user_name", "Alice", category="identity")
    mem.update_fact("user_age", "25", category="identity")
    mem.update_fact("favorite_color", "blue", category="preference")
    print("✓ Added 3 facts")
    
    # Retrieve
    fact = mem.get_fact("user_name")
    print(f"✓ Retrieved fact: {fact.key} = {fact.value}")
    
    # Get by category
    identity = mem.get_facts_by_category("identity")
    print(f"✓ Found {len(identity)} identity facts")
    
    return True


def test_procedural_memory():
    """Test procedural memory (recipes)."""
    print("\n=== Test Procedural Memory ===")
    mem = get_memory()
    
    # Add procedure
    proc = mem.add_procedure(
        name="make_coffee",
        description="How to make a good coffee",
        steps=[
            "Grind beans",
            "Heat water to 195-205°F",
            "Brew for 4 minutes",
            "Pour and enjoy",
        ],
        triggers=["coffee", "brew", "espresso"]
    )
    print(f"✓ Added procedure: {proc.name}")
    
    # Find by trigger
    found = mem.find_procedures_by_trigger("coffee")
    print(f"✓ Found {len(found)} procedures for 'coffee'")
    
    # Record success
    mem.record_procedure_success("make_coffee")
    proc_updated = mem.get_procedure("make_coffee")
    print(f"✓ Recorded success: {proc_updated.success_count} successes")
    
    return True


def test_rag_retrieval():
    """Test RAG cross-layer retrieval."""
    print("\n=== Test RAG Retrieval ===")
    mem = get_memory()
    
    # Clear and add diverse data
    reset_memory()
    mem = get_memory()
    
    # Working memory
    mem.add_turn("user", "I love programming", intent="hobby")
    mem.add_turn("assistant", "That's great! What languages do you know?", intent="question")
    
    # Episodic
    mem.write_episode(
        "conversation",
        "Discussed programming languages",
        entities=["programming", "languages"]
    )
    
    # Semantic
    mem.update_fact("programming_skill", "advanced", category="skill")
    mem.update_fact("favorite_lang", "Python", category="preference")
    
    # Procedural
    mem.add_procedure(
        name="learn_programming",
        description="Steps to learn a new programming language",
        steps=["Learn syntax", "Practice coding", "Build projects"],
        triggers=["learn", "programming", "language"]
    )
    
    # RAG retrieve
    print("\nRetrieving for 'programming'...")
    results = mem.retrieve("programming", k=5)
    print(f"✓ Retrieved {len(results)} results")
    
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.source:12} (score: {r.score:.2f})")
        print(f"      {r.text[:60]}...")
    
    # Get formatted context
    ctx = mem.get_retrieval_context("programming languages", k=3)
    print(f"\n✓ Formatted context:\n{ctx}")
    
    return True


def test_stats_and_export():
    """Test stats and export."""
    print("\n=== Test Stats & Export ===")
    mem = get_memory()
    
    # Stats
    stats = mem.stats()
    print(f"✓ Working memory: {stats['working']['size']}/{stats['working']['max']}")
    print(f"✓ Episodic: {stats['episodic'].get('total', 0)} events")
    print(f"✓ Semantic: {stats['semantic']['facts']} facts")
    print(f"✓ Procedural: {stats['procedural']['count']} procedures")
    
    # Export
    export = mem.export_all()
    print(f"✓ Exported memory keys: {list(export.keys())}")
    
    return True


def test_decay():
    """Test decay of old episodes."""
    print("\n=== Test Decay ===")
    mem = get_memory()
    
    # Get old stats
    before_stats = mem.episodic.stats()
    print(f"Before decay: {before_stats['total']} episodes")
    
    # Decay old episodes (>30 days)
    removed = mem.decay_old_episodes(days_threshold=30)
    print(f"✓ Removed {removed} old episodes")
    
    after_stats = mem.episodic.stats()
    print(f"After decay: {after_stats['total']} episodes")
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("MEMORY SYSTEM 4-LAYER INTEGRATION TESTS")
    print("=" * 60)
    
    tests = [
        test_working_memory,
        test_episodic_memory,
        test_semantic_memory,
        test_procedural_memory,
        test_rag_retrieval,
        test_stats_and_export,
        test_decay,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            result = test()
            if result:
                passed += 1
        except Exception as e:
                print(f"\nFAILED: Test failed: {e}")


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
