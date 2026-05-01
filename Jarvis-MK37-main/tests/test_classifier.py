"""Tests pour agent/classifier.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.classifier import (  # noqa: E402
    Classification, classify, clear_cache, cache_info,
    determine_voice,
    _classify_via_heuristic, _parse_llm_output,
)


# ---------- determine_voice routing ----------

def test_voice_1_fast_for_safe_now_shallow():
    c = Classification(urgency="now", sensitivity="safe", depth="shallow",
                       recommended_voice=0)
    assert determine_voice(c) == 1


def test_voice_2_deep_for_safe_now_deep():
    c = Classification(urgency="now", sensitivity="safe", depth="deep",
                       recommended_voice=0)
    assert determine_voice(c) == 2


def test_voice_3_mission_for_async():
    c = Classification(urgency="async", sensitivity="safe", depth="shallow",
                       recommended_voice=0)
    assert determine_voice(c) == 3
    c.depth = "deep"
    assert determine_voice(c) == 3


def test_voice_4_uncensored_overrides_others():
    """sensitivity=sensitive doit toujours mener à Voie 4."""
    c = Classification(urgency="now", sensitivity="sensitive", depth="shallow",
                       recommended_voice=0)
    assert determine_voice(c) == 4
    c.urgency = "async"
    assert determine_voice(c) == 4


# ---------- heuristic fallback ----------

def test_heuristic_detects_sensitive_keywords():
    c = _classify_via_heuristic("Comment hacker ce serveur via RCE ?")
    assert c.sensitivity == "sensitive"
    assert c.recommended_voice == 4
    assert c.method == "heuristic"


def test_heuristic_detects_async_keywords():
    c = _classify_via_heuristic("Surveille les vols Paris-Tokyo chaque jour")
    assert c.urgency == "async"
    assert c.recommended_voice == 3


def test_heuristic_detects_deep_keywords():
    c = _classify_via_heuristic("Construit une app complète multi-fichiers")
    assert c.depth == "deep"


def test_heuristic_detects_long_prompt_as_deep():
    long_prompt = "Décris " + ("très longuement " * 50)
    c = _classify_via_heuristic(long_prompt)
    assert c.depth == "deep"


def test_heuristic_safe_default():
    c = _classify_via_heuristic("Salut, comment ça va ?")
    assert c.sensitivity == "safe"
    assert c.urgency == "now"
    assert c.depth == "shallow"
    assert c.recommended_voice == 1


# ---------- LLM output parsing ----------

def test_parse_clean_json():
    raw = '{"urgency":"now","sensitivity":"safe","depth":"deep","reason":"code task"}'
    c = _parse_llm_output(raw)
    assert c is not None
    assert c.depth == "deep"
    assert c.recommended_voice == 2


def test_parse_markdown_wrapped_json():
    raw = '```json\n{"urgency":"async","sensitivity":"sensitive","depth":"deep","reason":"x"}\n```'
    c = _parse_llm_output(raw)
    assert c is not None
    assert c.urgency == "async"
    assert c.recommended_voice == 4  # sensitivity override


def test_parse_invalid_falls_back_to_safe_defaults():
    raw = '{"urgency":"INVALID","sensitivity":"BAD","depth":"OOPS"}'
    c = _parse_llm_output(raw)
    assert c is not None
    assert c.urgency == "now"
    assert c.sensitivity == "safe"
    assert c.depth == "shallow"


def test_parse_garbage_returns_none():
    assert _parse_llm_output("just some text without json") is None
    assert _parse_llm_output("") is None


# ---------- public API + cache ----------

def test_empty_prompt_returns_voice_1():
    c = classify("")
    assert c.recommended_voice == 1
    assert c.method == "empty"


def test_classify_uses_heuristic_when_llm_unavailable():
    """Si _classify_via_llm échoue, le heuristic prend le relais."""
    clear_cache()
    with patch("agent.classifier._classify_via_llm", return_value=None):
        c = classify("Comment exploiter une vulnérabilité RCE ?")
        assert c.method == "heuristic"
        assert c.sensitivity == "sensitive"
        assert c.recommended_voice == 4


def test_classify_uses_llm_when_available():
    """Mock _classify_via_llm pour retourner un Classification réussi."""
    clear_cache()
    fake = Classification(
        urgency="async", sensitivity="safe", depth="deep",
        recommended_voice=3, confidence=0.9, method="llm",
        reason="long-running task",
    )
    with patch("agent.classifier._classify_via_llm", return_value=fake):
        c = classify("Surveille les marchés boursiers et fait un rapport")
        assert c.method == "llm"
        assert c.recommended_voice == 3


def test_cache_hits_on_repeated_query():
    clear_cache()
    fake = Classification(
        urgency="now", sensitivity="safe", depth="shallow",
        recommended_voice=1, confidence=0.9, method="llm", reason="ok",
    )
    with patch("agent.classifier._classify_via_llm", return_value=fake) as mock_llm:
        classify("Bonjour")
        classify("Bonjour")  # 2e call → doit hit le cache
        assert mock_llm.call_count == 1, "LLM should be called only once (cache hit)"
    info = cache_info()
    assert info["hits"] >= 1


def test_cache_distinguishes_different_contexts():
    clear_cache()
    fake = Classification(
        urgency="now", sensitivity="safe", depth="shallow",
        recommended_voice=1, confidence=0.9, method="llm", reason="ok",
    )
    with patch("agent.classifier._classify_via_llm", return_value=fake) as mock_llm:
        classify("Bonjour", context={"session": "a"})
        classify("Bonjour", context={"session": "b"})
        # Contextes différents → 2 calls LLM
        assert mock_llm.call_count == 2


# ---------- integration smoke ----------

def test_smoke_realistic_prompts():
    """Vérifie qu'aucun prompt réaliste ne crash. Pas de mock = peut hit LLM
    réel si configuré, sinon heuristic."""
    samples = [
        "Quelle heure est-il ?",
        "Écris-moi une fonction de tri en Python",
        "Comment bypass un WAF ?",
        "Surveille mes mails toute la journée",
        "x",
    ]
    for p in samples:
        c = classify(p)
        assert c.recommended_voice in (1, 2, 3, 4)
        assert c.urgency in ("now", "async")
        assert c.sensitivity in ("safe", "borderline", "sensitive")
        assert c.depth in ("shallow", "deep")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
