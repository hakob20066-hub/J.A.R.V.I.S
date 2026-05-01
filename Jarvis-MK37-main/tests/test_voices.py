"""Tests pour agent/voices/* et agent/voice_router."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------- VoiceFast ----------

def test_voice_fast_returns_response():
    from agent.voices.voice_fast import VoiceFast

    fake_router = MagicMock()
    fake_router.generate.return_value = "Quick answer."
    fake_router.last_provider = "groq"

    with patch("agent.llm_router.get_router", return_value=fake_router):
        vf = VoiceFast()
        resp = vf.process("Bonjour")
        assert resp.voice_id == 1
        assert "Quick answer." in resp.text
        assert resp.elapsed_seconds >= 0


def test_voice_fast_falls_back_on_error():
    from agent.voices.voice_fast import VoiceFast

    fake_router = MagicMock()
    # Échec sur tous les FAST_PROVIDERS, puis succès en fallback global
    fake_router.generate.side_effect = [
        Exception("groq down"), Exception("cerebras down"),
        Exception("mistral down"), Exception("openrouter down"),
        "Final fallback response",
    ]
    fake_router.last_provider = "ollama"

    with patch("agent.llm_router.get_router", return_value=fake_router):
        vf = VoiceFast()
        resp = vf.process("test")
        assert resp.text == "Final fallback response"


# ---------- VoiceDeep ----------

def test_voice_deep_no_specialists_does_direct_answer():
    """Si supervisor retourne specialists vide → direct synthesis."""
    from agent.voices.voice_deep import VoiceDeep

    fake_router = MagicMock()
    fake_router.generate.side_effect = [
        '{"specialists": [], "synthesis_note": "réponse directe"}',  # plan
        "Direct answer text.",                                         # direct synth
    ]
    fake_router.last_provider = "anthropic"

    with patch("agent.llm_router.get_router", return_value=fake_router):
        vd = VoiceDeep()
        resp = vd.process("Quelle est la capitale de la France ?")
        assert resp.voice_id == 2
        assert "Direct answer" in resp.text
        assert resp.specialists_called == []


def test_voice_deep_with_specialists():
    """Plan avec 1 specialist → dispatch + synthèse + critique."""
    from agent.voices.voice_deep import VoiceDeep

    fake_router = MagicMock()
    fake_router.generate.side_effect = [
        # 1. plan
        '{"specialists": [{"name": "research", "subquery": "find X"}], "synthesis_note": "merge"}',
        # 2. specialist call (research)
        "Research result here.",
        # 3. synthesis
        "Final synthesized answer.",
        # 4. critique (high score → no retry)
        '{"score": 9, "issues": [], "fix": ""}',
    ]
    fake_router.last_provider = "anthropic"

    with patch("agent.llm_router.get_router", return_value=fake_router):
        vd = VoiceDeep()
        resp = vd.process("Recherche-moi des infos sur X")
        assert resp.voice_id == 2
        assert "Final synthesized" in resp.text
        assert "research" in resp.specialists_called


def test_voice_deep_critique_triggers_retry():
    """Score critique < 7 → 1 relance."""
    from agent.voices.voice_deep import VoiceDeep

    fake_router = MagicMock()
    fake_router.generate.side_effect = [
        # 1. plan
        '{"specialists": [{"name": "research", "subquery": "x"}], "synthesis_note": ""}',
        # 2. specialist
        "raw output",
        # 3. synthesis v1 (medium quality)
        "first draft answer",
        # 4. critique (score bas → retry)
        '{"score": 5, "issues": ["incomplete"], "fix": "add more detail"}',
        # 5. synthesis v2
        "improved answer",
        # 6. critique v2
        '{"score": 8, "issues": [], "fix": ""}',
    ]
    fake_router.last_provider = "anthropic"

    with patch("agent.llm_router.get_router", return_value=fake_router):
        vd = VoiceDeep()
        resp = vd.process("complex question")
        assert "improved" in resp.text
        assert resp.metadata["retries"] == 1


# ---------- VoiceUncensored ----------

def test_voice_uncensored_direct_answer():
    """Quand le superviseur local répond direct sans déléguer."""
    from agent.voices.voice_uncensored import VoiceUncensored

    fake_provider = MagicMock()
    fake_provider.backend = "ollama"
    fake_provider.model = "qwen2.5-abliterate:14b"
    fake_provider._warmed = True
    fake_provider.generate.return_value = (
        '{"specialists": [], "direct_answer": "Voici la réponse sans filtre."}'
    )

    with patch("agent.local_llm_provider.get_local_provider", return_value=fake_provider):
        vu = VoiceUncensored()
        resp = vu.process("Comment exploiter X ?")
        assert resp.voice_id == 4
        assert "sans filtre" in resp.text


def test_voice_uncensored_falls_back_to_raw_generate():
    """Plan invalide → fallback raw generate sans plan."""
    from agent.voices.voice_uncensored import VoiceUncensored

    fake_provider = MagicMock()
    fake_provider.backend = "ollama"
    fake_provider.model = "qwen"
    fake_provider._warmed = True
    fake_provider.generate.side_effect = [
        "garbage no json",        # plan parsing échoue
        "raw uncensored answer",  # fallback direct
    ]

    with patch("agent.local_llm_provider.get_local_provider", return_value=fake_provider):
        vu = VoiceUncensored()
        resp = vu.process("test")
        assert resp.text == "raw uncensored answer"


# ---------- VoiceRouter ----------

def test_voice_router_routes_to_voice_1_for_safe_shallow():
    from agent import voice_router as vr
    from agent.classifier import Classification

    fake_cls = Classification(
        urgency="now", sensitivity="safe", depth="shallow",
        recommended_voice=1, confidence=0.9, method="llm", reason="trivial",
    )
    fake_resp = MagicMock(text="fast answer", refusal_detected=False, metadata={})

    with patch("agent.voice_router.classify", return_value=fake_cls), \
         patch("agent.voice_router._get_voice") as get_voice_mock:
        voice_mock = MagicMock()
        voice_mock.process.return_value = fake_resp
        get_voice_mock.return_value = voice_mock

        vr.process("Salut")
        get_voice_mock.assert_called_with(1)


def test_voice_router_falls_back_to_voice_4_on_refusal():
    """Voie 1 retourne un refus → on doit re-route vers Voie 4."""
    from agent import voice_router as vr
    from agent.classifier import Classification
    from agent.voices.base import VoiceResponse

    fake_cls = Classification(
        urgency="now", sensitivity="safe", depth="shallow",
        recommended_voice=1, confidence=0.9, method="llm", reason="x",
    )
    refused = VoiceResponse(
        text="I can't help with that, sorry.", voice_id=1, provider_used="groq",
    )
    uncensored_resp = VoiceResponse(
        text="Voici la réponse sans filtre.", voice_id=4, provider_used="ollama",
    )

    voice_1 = MagicMock(); voice_1.process.return_value = refused
    voice_4 = MagicMock(); voice_4.process.return_value = uncensored_resp

    def get_voice_side(vid):
        return {1: voice_1, 4: voice_4}[vid]

    with patch("agent.voice_router.classify", return_value=fake_cls), \
         patch("agent.voice_router._get_voice", side_effect=get_voice_side):
        resp = vr.process("question")
        assert resp.voice_id == 4
        assert "sans filtre" in resp.text
        assert resp.metadata.get("fallback_from_voice") == 1


def test_voice_router_does_not_fallback_when_no_refusal():
    from agent import voice_router as vr
    from agent.classifier import Classification
    from agent.voices.base import VoiceResponse

    fake_cls = Classification(
        urgency="now", sensitivity="safe", depth="shallow",
        recommended_voice=1, confidence=0.9, method="llm", reason="x",
    )
    normal = VoiceResponse(
        text="Voici la réponse complète et utile.", voice_id=1, provider_used="groq",
    )
    voice_1 = MagicMock(); voice_1.process.return_value = normal

    with patch("agent.voice_router.classify", return_value=fake_cls), \
         patch("agent.voice_router._get_voice", return_value=voice_1):
        resp = vr.process("question simple")
        assert resp.voice_id == 1
        assert not resp.refusal_detected


def test_voice_router_voice_3_schedules_mission():
    from agent import voice_router as vr
    from agent.classifier import Classification

    fake_cls = Classification(
        urgency="async", sensitivity="safe", depth="shallow",
        recommended_voice=3, confidence=0.9, method="llm", reason="long task",
    )
    with patch("agent.voice_router.classify", return_value=fake_cls):
        # mission_store peut être absent ou réel — on tolère les 2
        resp = vr.process("Surveille les vols Paris-Tokyo")
        # Soit mission planifiée (voice_id=3), soit fallback Voie 2 (voice_id=2)
        assert resp.voice_id in (2, 3)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
