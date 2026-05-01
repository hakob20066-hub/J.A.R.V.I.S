"""
Voice Router — point d'entrée unifié pour toutes les voix cognitives.

Workflow :
  1. classify(query) → Classification (3 axes + recommended_voice)
  2. dispatch vers la voie 1/2/3/4 correspondante
  3. detect refusal sur l'output
  4. si refus → re-route auto vers Voie 4 (UNCENSORED)
  5. retourne VoiceResponse

Voie 3 (mission async) : route immédiat vers mission_runner, retourne un
VoiceResponse de type "mission scheduled" sans bloquer l'utilisateur.
"""

from __future__ import annotations

from typing import Optional

from agent.classifier import Classification, classify
from agent.refusal_detector import is_refusal, refusal_score
from agent.voices import VoiceResponse
from agent.voices.voice_deep import VoiceDeep
from agent.voices.voice_fast import VoiceFast
from agent.voices.voice_uncensored import VoiceUncensored


# Singletons (créés à la première utilisation)
_VOICE_FAST: Optional[VoiceFast] = None
_VOICE_DEEP: Optional[VoiceDeep] = None
_VOICE_UNCENSORED: Optional[VoiceUncensored] = None


def _get_voice(voice_id: int):
    global _VOICE_FAST, _VOICE_DEEP, _VOICE_UNCENSORED
    if voice_id == 1:
        if _VOICE_FAST is None:
            _VOICE_FAST = VoiceFast()
        return _VOICE_FAST
    if voice_id == 2:
        if _VOICE_DEEP is None:
            _VOICE_DEEP = VoiceDeep()
        return _VOICE_DEEP
    if voice_id == 4:
        if _VOICE_UNCENSORED is None:
            _VOICE_UNCENSORED = VoiceUncensored()
        return _VOICE_UNCENSORED
    raise ValueError(f"Voice {voice_id} not handled by voice_router (mission=3 va dans mission_runner)")


REFUSAL_SCORE_THRESHOLD = 0.5


def process(query: str, context: Optional[dict] = None) -> VoiceResponse:
    """
    Pipeline complet :
      classify → voice 1/2/4 sync → refusal check → fallback uncensored si refus
      voie 3   → schedule mission async, retourne tout de suite
    """
    cls = classify(query, context=context)
    print(f"[VoiceRouter] 🧠 Voie {cls.recommended_voice} "
          f"({cls.urgency}/{cls.sensitivity}/{cls.depth}, {cls.method}) — {cls.reason}")

    # Voie 3 : mission async
    if cls.recommended_voice == 3:
        return _schedule_mission(query, cls, context)

    # Voies 1, 2, 4 : synchrone
    voice = _get_voice(cls.recommended_voice)
    response = voice.process(query, context)

    # Si Voie 1 ou 2 : check refus → fallback Voie 4
    if cls.recommended_voice in (1, 2):
        score = refusal_score(response.text)
        if is_refusal(response.text) or score >= REFUSAL_SCORE_THRESHOLD:
            print(f"[VoiceRouter] 🔄 refus détecté (score {score:.2f}) → fallback Voie 4")
            response.refusal_detected = True
            uncensored = _get_voice(4)
            new_response = uncensored.process(query, context)
            new_response.metadata["fallback_from_voice"] = cls.recommended_voice
            new_response.metadata["original_refusal"] = response.text[:300]
            return new_response

    return response


def _schedule_mission(query: str, cls: Classification, context: Optional[dict]) -> VoiceResponse:
    """Voie 3 : enqueue dans mission_store, retourne tout de suite."""
    try:
        from agent.mission_store import MissionStore
        from agent.mission_models import Mission
        import uuid
        from datetime import datetime

        store = MissionStore()
        mission = Mission(
            id=str(uuid.uuid4()),
            description=query,
            status="pending",
            created_at=datetime.now().isoformat(timespec="seconds"),
            metadata={
                "classification": cls.__dict__,
                "context": context or {},
                "voice_used": 3,
            },
        )
        store.add(mission)
        text = (
            f"🎯 Mission planifiée (#{mission.id[:8]}). "
            f"Je traite ça en arrière-plan, je te notifie quand c'est prêt."
        )
        return VoiceResponse(
            text=text,
            voice_id=3,
            provider_used="mission_runner",
            metadata={"mission_id": mission.id, "classification": cls.__dict__},
        )
    except Exception as e:
        # Fallback : si mission_store indisponible, traite en Voie 2 sync
        print(f"[VoiceRouter] ⚠️ mission_store indispo ({e}) → fallback Voie 2")
        voice = _get_voice(2)
        return voice.process(query, context)


def reset_voices() -> None:
    """Force réinit de tous les singletons (tests, hot-reload)."""
    global _VOICE_FAST, _VOICE_DEEP, _VOICE_UNCENSORED
    _VOICE_FAST = None
    _VOICE_DEEP = None
    _VOICE_UNCENSORED = None
