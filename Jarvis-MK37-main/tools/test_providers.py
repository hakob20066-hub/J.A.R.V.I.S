"""Test de connexion de tous les providers LLM configurés."""
import sys
from pathlib import Path

# Ajout racine projet au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.llm_router import LLMRouter, DEFAULT_CHAIN


def test_all():
    r = LLMRouter()
    prompt = "Reply with only: OK"
    results = {}

    for provider in DEFAULT_CHAIN:
        available = r._provider_available(provider)
        if not available:
            results[provider] = ("SKIP", "no key")
            continue
        try:
            model = r.models.get(provider)
            out = r._dispatch(provider, prompt, "", model, 0.0, 20)
            ok = "ok" in out.lower() or len(out) > 0
            results[provider] = ("OK" if ok else "EMPTY", f"{model} → {out[:40]}")
        except Exception as e:
            msg = str(e)[:120]
            results[provider] = ("FAIL", msg)

    print("\n=== RESULTATS ===")
    for p, (status, detail) in results.items():
        emoji = {"OK": "✅", "SKIP": "⚪", "EMPTY": "⚠️", "FAIL": "❌"}[status]
        print(f"{emoji} {p:12s} {status:6s} {detail}")
    print()


if __name__ == "__main__":
    test_all()
