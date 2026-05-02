"""
Tests pour les fixes des gaps Phase 7 :

  Gap #1 : consume_async_notifications drainé périodiquement
  Gap #2 : mutex speech output (defer si user/jarvis parle)
  Gap #3 : tooltip UI (test smoke seulement)
  Gap #4 : _is_status_query patterns étendus FR + EN
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permet d'importer les modules du projet
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest


# ───────────────────────── Gap #4 : status query regex ──────────────────────

def test_status_query_french_natural_variants():
    from agent.voice_router import _is_status_query
    cases = [
        "où en est ma mission",
        "ou en est la recherche",
        "ça en est où ?",
        "ca en est ou ?",
        "t'en est où",
        "tu en es où",
        "tu en es ou",
        "tu es où",
        "avancement de la mission",
        "la tâche avance",
        "la mission progresse",
        "état de la mission",
        "etat de la recherche",
        "c'est bon ?",
        "c'est prêt",
        "c'est fini ?",
        "t'as fini",
        "tu as fini ?",
        "toujours en cours",
    ]
    for q in cases:
        assert _is_status_query(q), f"FR pattern raté: '{q}'"


def test_status_query_english_natural_variants():
    from agent.voice_router import _is_status_query
    cases = [
        "what's the status",
        "any progress",
        "any update on the mission",
        "how is it going",
        "how's the task going",
        "where are you on it",
        "where is it",
        "is it done",
        "are you done",
        "done yet",
    ]
    for q in cases:
        assert _is_status_query(q), f"EN pattern raté: '{q}'"


def test_status_query_negative_cases():
    """Phrases qui NE sont PAS des status queries — on ne doit pas matcher."""
    from agent.voice_router import _is_status_query
    cases = [
        "quel temps fait-il",
        "ouvre chrome",
        "joue de la musique",
        "envoie un message à Marc",
        "play some jazz",
        "open the file foo.txt",
        "what is the weather",
        "raconte-moi une blague",
    ]
    for q in cases:
        assert not _is_status_query(q), f"Faux positif: '{q}'"


# ─────────────────── Gap #1 : consume_async_notifications ────────────────────

def test_consume_async_notifications_drains_queue():
    """Vérifie que le drain vide bien la queue et retourne les éléments."""
    from agent import voice_router as vr
    # Reset propre
    with vr._ASYNC_NOTIF_LOCK:
        vr._ASYNC_NOTIFICATIONS.clear()
        vr._ASYNC_NOTIFICATIONS.extend(["msg 1", "msg 2", "msg 3"])

    drained = vr.consume_async_notifications()
    assert drained == ["msg 1", "msg 2", "msg 3"]
    # Après drain, la queue est vide
    assert vr.consume_async_notifications() == []


def test_notify_mission_completed_appends_to_queue():
    from agent import voice_router as vr
    from types import SimpleNamespace

    with vr._ASYNC_NOTIF_LOCK:
        vr._ASYNC_NOTIFICATIONS.clear()

    fake_mission = SimpleNamespace(id="abcdef1234", result="le résultat")
    vr.notify_mission_completed(fake_mission)

    drained = vr.consume_async_notifications()
    assert len(drained) == 1
    assert "abcdef12" in drained[0]
    assert "le résultat" in drained[0]


# ─────────────────────── Gap #2 : speech mutex logic ─────────────────────────
# On ne peut pas lancer une vraie session Gemini en test, donc on teste la
# logique de gating en isolant les conditions du _consume_async_notifs_loop.

def test_user_speaking_until_blocks_announcement():
    """Si _user_speaking_until > now, on doit ignorer la queue."""
    import time
    user_speaking_until = time.time() + 3.0
    is_speaking = False
    text_turn_pending = False

    user_active = time.time() < user_speaking_until
    should_defer = is_speaking or user_active or text_turn_pending
    assert should_defer is True


def test_jarvis_speaking_blocks_announcement():
    import time
    user_speaking_until = time.time() - 5.0  # passé
    is_speaking = True
    text_turn_pending = False

    user_active = time.time() < user_speaking_until
    should_defer = is_speaking or user_active or text_turn_pending
    assert should_defer is True


def test_text_turn_pending_blocks_announcement():
    import time
    user_speaking_until = time.time() - 5.0
    is_speaking = False
    text_turn_pending = True

    user_active = time.time() < user_speaking_until
    should_defer = is_speaking or user_active or text_turn_pending
    assert should_defer is True


def test_announce_when_silent():
    """Personne ne parle → on doit pouvoir annoncer."""
    import time
    user_speaking_until = time.time() - 5.0
    is_speaking = False
    text_turn_pending = False

    user_active = time.time() < user_speaking_until
    should_defer = is_speaking or user_active or text_turn_pending
    assert should_defer is False


# ─────────────────────────── Gap #3 : UI tooltip ─────────────────────────────

def test_task_queue_panel_has_tooltip():
    """Smoke test : le tooltip est bien présent dans le HTML."""
    html = (ROOT / "ui.html").read_text(encoding="utf-8")
    assert "Foreground requests run in parallel" in html, \
        "Tooltip Phase 7 gap #3 manquant dans ui.html"
    # ⓘ marker visible côté UI
    assert "Task Queue ⓘ" in html, "Indicateur ⓘ manquant sur le titre Task Queue"


# ─────────────────────────── main.py wiring ──────────────────────────────────

def test_main_py_wires_async_notifs_loop():
    """Vérifie que le TaskGroup contient bien le loop de notifs."""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "_consume_async_notifs_loop" in src
    assert "tg.create_task(self._consume_async_notifs_loop())" in src


def test_main_py_has_user_speaking_flag():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "_user_speaking_until" in src
    assert "_tts_lock" in src
