"""Tests pour agent/refusal_detector.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.refusal_detector import (  # noqa: E402
    is_refusal, refusal_score, find_refusal_phrase,
)


# ---------- hard refusals ----------

def test_detects_english_hard_refusals():
    assert is_refusal("I can't help you with that, sorry.")
    assert is_refusal("I cannot provide instructions for hacking.")
    assert is_refusal("I'm not able to assist with this request.")
    assert is_refusal("As an AI, I must decline.")
    assert is_refusal("I'm sorry, but I can't go down this path.")


def test_detects_french_hard_refusals():
    assert is_refusal("Je ne peux pas répondre à cette question.")
    assert is_refusal("Désolé, je ne peux pas faire ça.")
    assert is_refusal("Il m'est impossible de fournir cette information.")
    assert is_refusal("En tant qu'IA, je dois décliner.")
    assert is_refusal("Cela va à l'encontre de mes principes.")


def test_detects_spanish_hard_refusals():
    assert is_refusal("Lo siento, pero no puedo ayudarte con eso.")
    assert is_refusal("Como una IA, no puedo proporcionar esta información.")


# ---------- soft refusals ----------

def test_detects_soft_refusals_when_short():
    # Soft refusal courte = considérée refus
    assert is_refusal("This might not be appropriate. Try asking elsewhere.")
    assert is_refusal("Je préfère ne pas répondre à ça.")
    assert is_refusal("I'd rather not go into that.")


def test_soft_refusal_in_long_helpful_response_is_not_refusal():
    """Si l'IA dit 'I'd rather not...' MAIS répond quand même longuement = ok."""
    text = (
        "I'd rather not jump straight to the answer without context, but here we go. "
        + "Detail. " * 200
    )
    assert not is_refusal(text)


# ---------- non-refusals ----------

def test_normal_responses_are_not_refusals():
    assert not is_refusal("Voici la réponse à ta question : ...")
    assert not is_refusal("The answer is 42.")
    assert not is_refusal("")
    assert not is_refusal("Hello! Sure thing, here's how to do that.")


def test_long_technical_response_not_refusal():
    text = "To exploit a buffer overflow you need to: 1. find the offset, 2. ..."
    assert not is_refusal(text)


# ---------- soft=False mode ----------

def test_soft_false_only_catches_hard():
    """Avec soft=False, les refus mous ne sont pas détectés."""
    soft_text = "I'd rather not discuss this."
    assert is_refusal(soft_text, soft=True)
    assert not is_refusal(soft_text, soft=False)

    hard_text = "I cannot help with that."
    assert is_refusal(hard_text, soft=False)


# ---------- score ----------

def test_score_increases_with_more_signals():
    weak = "I prefer not to."
    strong = "I'm sorry, but as an AI, I cannot help with that. It's against my guidelines."
    assert refusal_score(strong) > refusal_score(weak)
    assert refusal_score(strong) > 0.5


def test_score_zero_for_normal_text():
    assert refusal_score("Voici la réponse complète.") < 0.3


def test_score_short_with_keyword():
    assert refusal_score("Sorry, can't.") > 0.4


# ---------- find_refusal_phrase ----------

def test_find_refusal_phrase_returns_match():
    text = "Voici un préambule. Je ne peux pas répondre à cette question."
    phrase = find_refusal_phrase(text)
    assert "peux pas" in phrase.lower() or "ne peux" in phrase.lower()


def test_find_refusal_phrase_returns_empty_for_normal():
    assert find_refusal_phrase("Tout va bien, voici la réponse.") == ""


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
