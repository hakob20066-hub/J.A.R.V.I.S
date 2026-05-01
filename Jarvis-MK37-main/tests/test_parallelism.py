"""Tests for Phase 7 foreground/background parallelism."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.flow_manager import get_flow_manager, reset_flow_manager  # noqa: E402
from agent.mission_models import Mission  # noqa: E402
from agent.mission_runner import MissionRunner  # noqa: E402
from agent.mission_store import MissionStore  # noqa: E402
from agent.voices.base import VoiceResponse  # noqa: E402


def _make_store() -> MissionStore:
    tmp_dir = Path(tempfile.mkdtemp())
    return MissionStore(tmp_dir / "missions.json")


def test_query_mission_status_without_missions():
    from agent import voice_router as vr

    store = _make_store()
    with patch("agent.voice_router._STORE", store):
        txt = vr.query_mission_status()
        assert "Aucune mission en cours" in txt


def test_query_mission_status_reports_progress_and_step():
    from agent import voice_router as vr

    store = _make_store()
    m = Mission(id="m1", description="parse pdf", status="running", progress=0.4)
    m.metadata["current_step"] = "parser le PDF"
    store.add(m)
    with patch("agent.voice_router._STORE", store):
        txt = vr.query_mission_status("m1")
        assert "40%" in txt
        assert "parser le PDF" in txt


def test_status_query_uses_fast_control_path():
    from agent import voice_router as vr

    with patch("agent.voice_router.classify", side_effect=AssertionError("classify should not run")):
        resp = vr.process("Où en est ton travail ?")
    assert resp.voice_id == 1
    assert resp.metadata.get("status_query") is True


def test_foreground_interrupt_forces_voice_fast_when_low_active():
    from agent import voice_router as vr

    reset_flow_manager()
    flow = get_flow_manager()
    flow.register_low_task("mission-1", "long background job")

    fast_voice = MagicMock()
    fast_voice.process.return_value = VoiceResponse(text="fast reply", voice_id=1, provider_used="mock")

    with patch("agent.voice_router._get_voice", return_value=fast_voice), \
         patch("agent.voice_router.classify", side_effect=AssertionError("classify should not run")):
        resp = vr.process("Réponds vite pendant la mission")

    assert resp.voice_id == 1
    assert "fast reply" in resp.text


def test_mission_runner_completion_emits_async_notification():
    from agent import voice_router as vr

    store = _make_store()
    mission = Mission(id="cb1", description="heavy job", status="running", progress=0.4)
    store.add(mission, force=True)
    reset_flow_manager()
    get_flow_manager().register_low_task("cb1", "heavy job")

    runner = MissionRunner(store=store, max_workers=1, poll_interval=0.01)
    with patch.object(runner, "_dispatch_to_voice", return_value="result ok"):
        runner._register_default_callbacks()
        runner._run_mission(mission)

    notifications = vr.consume_async_notifications()
    assert any("terminé la mission cb1" in n for n in notifications)
    assert get_flow_manager().get_task("cb1").status == "done"
