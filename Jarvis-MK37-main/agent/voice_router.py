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

import re
import threading
from typing import Optional

from agent.classifier import Classification, classify
from agent.flow_manager import get_flow_manager
from agent.mission_store import MissionStore
from agent.refusal_detector import is_refusal, refusal_score
from agent.voices import VoiceResponse
from agent.voices.voice_deep import VoiceDeep
from agent.voices.voice_fast import VoiceFast
from agent.voices.voice_mission import VoiceMission
from agent.voices.voice_uncensored import VoiceUncensored


# Singletons (créés à la première utilisation)
_VOICE_FAST: Optional[VoiceFast] = None
_VOICE_DEEP: Optional[VoiceDeep] = None
_VOICE_MISSION: Optional[VoiceMission] = None
_VOICE_UNCENSORED: Optional[VoiceUncensored] = None

_STORE = MissionStore()
_ASYNC_NOTIF_LOCK = threading.RLock()
_ASYNC_NOTIFICATIONS: list[str] = []


def _get_voice(voice_id: int):
    global _VOICE_FAST, _VOICE_DEEP, _VOICE_MISSION, _VOICE_UNCENSORED
    if voice_id == 1:
        if _VOICE_FAST is None:
            _VOICE_FAST = VoiceFast()
        return _VOICE_FAST
    if voice_id == 2:
        if _VOICE_DEEP is None:
            _VOICE_DEEP = VoiceDeep()
        return _VOICE_DEEP
    if voice_id == 3:
        if _VOICE_MISSION is None:
            _VOICE_MISSION = VoiceMission()
        return _VOICE_MISSION
    if voice_id == 4:
        if _VOICE_UNCENSORED is None:
            _VOICE_UNCENSORED = VoiceUncensored()
        return _VOICE_UNCENSORED
    raise ValueError(f"Unknown voice_id: {voice_id}")


REFUSAL_SCORE_THRESHOLD = 0.5


def _is_status_query(query: str) -> bool:
    q = (query or "").lower()
    patterns = (
        r"où en est",
        r"ou en est",
        r"avancement",
        r"status",
        r"progress",
        r"where.*work",
        r"where.*mission",
        r"etat.*mission",
    )
    return any(re.search(p, q) for p in patterns)


def _extract_mission_id(query: str) -> Optional[str]:
    m = re.search(r"([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})", query or "", re.IGNORECASE)
    return m.group(1) if m else None


def query_mission_status(mission_id: Optional[str] = None) -> str:
    mission = None
    if mission_id:
        mission = _STORE.get(mission_id)

    if mission is None:
        running = _STORE.get_running()
        pending = _STORE.get_pending()
        done = _STORE.get_done()
        if running:
            mission = sorted(running, key=lambda m: m.created_at)[0]
        elif pending:
            mission = sorted(pending, key=lambda m: m.created_at)[0]
        elif done:
            mission = sorted(done, key=lambda m: m.completed_at or "", reverse=True)[0]

    if mission is None:
        return "🟢[FAST] Aucune mission en cours pour le moment."

    progress_pct = int((mission.progress or 0.0) * 100)
    step = mission.metadata.get("current_step") or "analyse en cours"
    if mission.status == "done":
        return f"🟢[FAST] La tâche {mission.id[:8]} est terminée. Résultat prêt."
    if mission.status == "failed":
        return f"🟢[FAST] La tâche {mission.id[:8]} a échoué: {mission.error or 'erreur inconnue'}."
    return (
        f"🟢[FAST] La tâche {mission.id[:8]} est à {progress_pct}%, "
        f"je suis en train de {step}."
    )


def notify_mission_completed(mission) -> None:
    text = f"🟣[MISSION] J'ai terminé la mission {mission.id[:8]}, voici le résultat: {mission.result or 'OK'}"
    with _ASYNC_NOTIF_LOCK:
        _ASYNC_NOTIFICATIONS.append(text)
    print(text)


def consume_async_notifications() -> list[str]:
    with _ASYNC_NOTIF_LOCK:
        out = list(_ASYNC_NOTIFICATIONS)
        _ASYNC_NOTIFICATIONS.clear()
        return out


def process(query: str, context: Optional[dict] = None) -> VoiceResponse:
    """
    Pipeline complet :
      classify → voice 1/2/4 sync → refusal check → fallback uncensored si refus
      voie 3   → schedule mission async, retourne tout de suite
    """
    flow = get_flow_manager()
    flow.register_high_request(query)

    if _is_status_query(query):
        mission_id = _extract_mission_id(query)
        status_text = query_mission_status(mission_id)
        return VoiceResponse(
            text=status_text,
            voice_id=1,
            provider_used="mission_store",
            metadata={"status_query": True, "mission_id": mission_id},
        )

    if flow.has_active_low_priority():
        print(f"[VoiceRouter] 🟢[FAST] Foreground interrupt with {flow.active_low_count()} background task(s)")
        fast = _get_voice(1)
        return fast.process(query, context)

    cls = classify(query, context=context)
    print(f"[VoiceRouter] 🧠 Voie {cls.recommended_voice} "
          f"({cls.urgency}/{cls.sensitivity}/{cls.depth}, {cls.method}) — {cls.reason}")

    # Voies 1, 2, 3, 4 : dispatch via _get_voice
    # (Voie 3 = VoiceMission qui schedule async et retourne mission_id)
    voice = _get_voice(cls.recommended_voice)
    response = voice.process(query, context)

    if cls.recommended_voice == 3:
        mid = response.metadata.get("mission_id") if response.metadata else None
        if mid:
            flow.register_low_task(mid, query)

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


def reset_voices() -> None:
    """Force réinit de tous les singletons (tests, hot-reload)."""
    global _VOICE_FAST, _VOICE_DEEP, _VOICE_MISSION, _VOICE_UNCENSORED
    _VOICE_FAST = None
    _VOICE_DEEP = None
    _VOICE_MISSION = None
    _VOICE_UNCENSORED = None
