"""
Test d'intégration du système de mémoire 4 couches + RAG (simplifié).
"""

import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory import get_memory, reset_memory


def main():
    """Run basic test."""
    print("=" * 60)
    print("MEMORY SYSTEM 4-LAYER INTEGRATION TEST")
    print("=" * 60)
    
    try:
        # Test 1: Import
        print("\n[1] Testing imports...")
        mem = get_memory()
        print("    [OK] get_memory() works")
        
        # Test 2: Working memory
        print("\n[2] Testing working memory...")
        for i in range(25):
            mem.add_turn("user", f"Message {i}", intent="test")
        size = mem.working.size()
        print(f"    [OK] FIFO works: {size}/20 turns")
        assert size == 20
        
        # Test 3: Episodic memory
        print("\n[3] Testing episodic memory...")
        ep_id = mem.write_episode(
            "conversation",
            "User asked about memory system",
            details={"topic": "memory"},
            entities=["memory"]
        )
        print(f"    [OK] Episode written: {ep_id}")
        recent = mem.get_recent_episodes(n=1)
        print(f"    [OK] Retrieved {len(recent)} recent episodes")
        
        # Test 4: Semantic memory
        print("\n[4] Testing semantic memory...")
        mem.update_fact("user_name", "Alice", category="identity")
        mem.update_fact("user_age", "25", category="identity")
        fact = mem.get_fact("user_name")
        print(f"    [OK] Fact saved: {fact.key} = {fact.value}")
        identity_facts = mem.get_facts_by_category("identity")
        print(f"    [OK] Retrieved {len(identity_facts)} identity facts")
        
        # Test 5: Procedural memory
        print("\n[5] Testing procedural memory...")
        proc = mem.add_procedure(
            name="test_proc",
            description="Test procedure",
            steps=["Step 1", "Step 2"],
            triggers=["test"]
        )
        print(f"    [OK] Procedure saved: {proc.name}")
        mem.record_procedure_success("test_proc")
        reliability = proc.reliability()
        print(f"    [OK] Success recorded, reliability: {reliability:.2f}")
        
        # Test 6: RAG Retrieval
        print("\n[6] Testing RAG retrieval...")
        results = mem.retrieve("memory", k=3)
        print(f"    [OK] Retrieved {len(results)} results from RAG")
        for i, r in enumerate(results, 1):
            print(f"        [{i}] {r.source}: {r.text[:50]}...")
        
        # Test 7: Stats
        print("\n[7] Testing stats...")
        stats = mem.stats()
        print(f"    [OK] Working: {stats['working']['size']}/{stats['working']['max']}")
        print(f"    [OK] Episodic: {stats['episodic'].get('total', 0)} events")
        print(f"    [OK] Semantic: {stats['semantic']['facts']} facts")
        print(f"    [OK] Procedural: {stats['procedural']['count']} procedures")
        
        # Test 8: Format for prompt
        print("\n[8] Testing format_for_prompt...")
        prompt_ctx = mem.format_for_prompt()
        print(f"    [OK] Generated {len(prompt_ctx)} chars of context")
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n[FAILED] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
