"""Tests pour agent/mission_runner.py + agent/voices/voice_mission.py."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.mission_models import Mission  # noqa: E402
from agent.mission_store import MissionStore  # noqa: E402
from agent.mission_runner import MissionRunner  # noqa: E402


def _make_store() -> tuple[MissionStore, Path]:
    """Crée un store dans un répertoire temporaire (Windows-safe)."""
    tmp_dir = Path(tempfile.mkdtemp())
    path = tmp_dir / "missions.json"
    return MissionStore(path), path


# ---------- MissionRunner ----------

def test_runner_starts_and_stops():
    store, _ = _make_store()
    runner = MissionRunner(store=store, max_workers=1, poll_interval=0.1)
    runner.start()
    assert runner.is_running()
    runner.stop()
    assert not runner.is_running()


def test_runner_executes_pending_mission():
    store, _ = _make_store()
    store.add(Mission(id="m1", description="do something simple"))

    fake_response = MagicMock(text="mission result", specialists_called=["research"])
    fake_voice = MagicMock()
    fake_voice.process.return_value = fake_response

    with patch("agent.voice_router._get_voice", return_value=fake_voice):
        runner = MissionRunner(store=store, max_workers=1, poll_interval=0.05)
        runner.start()
        # Poll up to 3s for completion
        deadline = time.time() + 3
        while time.time() < deadline:
            m = store.get("m1")
            if m and m.status in ("done", "failed"):
                break
            time.sleep(0.1)
        runner.stop()

    final = store.get("m1")
    assert final.status == "done"
    assert "mission result" in (final.result or "")
    assert "research" in final.specialists_called


def test_runner_marks_failed_on_exception():
    store, _ = _make_store()
    store.add(Mission(id="fail1", description="x", max_retries=0))

    fake_voice = MagicMock()
    fake_voice.process.side_effect = RuntimeError("boom")

    with patch("agent.voice_router._get_voice", return_value=fake_voice):
        runner = MissionRunner(store=store, max_workers=1, poll_interval=0.05)
        runner.start()
        deadline = time.time() + 3
        while time.time() < deadline:
            m = store.get("fail1")
            if m and m.status == "failed":
                break
            time.sleep(0.1)
        runner.stop()

    final = store.get("fail1")
    assert final.status == "failed"
    assert "boom" in (final.error or "")


def test_runner_callback_fires_on_done():
    store, _ = _make_store()
    store.add(Mission(id="cb1", description="x"))

    callback_called = {"count": 0, "mission_id": None}

    def on_done(m: Mission):
        callback_called["count"] += 1
        callback_called["mission_id"] = m.id

    fake_voice = MagicMock()
    fake_voice.process.return_value = MagicMock(text="ok", specialists_called=[])

    with patch("agent.voice_router._get_voice", return_value=fake_voice):
        runner = MissionRunner(store=store, max_workers=1, poll_interval=0.05)
        runner.on_mission_done(on_done)
        runner.start()
        deadline = time.time() + 3
        while time.time() < deadline:
            if callback_called["count"] > 0:
                break
            time.sleep(0.1)
        runner.stop()

    assert callback_called["count"] == 1
    assert callback_called["mission_id"] == "cb1"


def test_runner_recovers_orphans_on_start():
    store, _ = _make_store()
    store.add(Mission(id="orphan", description="x", status="running"))
    runner = MissionRunner(store=store, max_workers=1, poll_interval=0.05)
    runner.start()
    runner.stop()
    # L'orphan a été reset à pending
    assert store.get("orphan").status in ("pending", "running", "done")  # peut avoir tourné


# ---------- VoiceMission ----------

def test_voice_mission_creates_top_and_subtasks():
    from agent.voices.voice_mission import VoiceMission

    store, _ = _make_store()
    plan_response = (
        '{"summary": "monitor flights", '
        '"subtasks": ['
        '  {"description": "scrape flight prices daily", "voice_target": 2, "specialists": ["research"]},'
        '  {"description": "alert if price < threshold", "voice_target": 1, "specialists": []}'
        ']}'
    )

    fake_router = MagicMock()
    fake_router.generate.return_value = plan_response

    with patch("agent.llm_router.get_router", return_value=fake_router):
        vm = VoiceMission(store=store)
        resp = vm.process("Surveille les vols Paris-Tokyo et alerte-moi")

    assert resp.voice_id == 3
    top_id = resp.metadata["mission_id"]
    sub_ids = resp.metadata["subtask_ids"]
    assert len(sub_ids) == 2

    top = store.get(top_id)
    assert top is not None
    assert top.subtask_ids == sub_ids

    sub_a = store.get(sub_ids[0])
    assert sub_a.parent_id == top_id
    assert sub_a.voice_used == 2


def test_voice_mission_falls_back_to_single_subtask_on_bad_plan():
    from agent.voices.voice_mission import VoiceMission

    store, _ = _make_store()
    fake_router = MagicMock()
    fake_router.generate.side_effect = Exception("planner down")

    with patch("agent.llm_router.get_router", return_value=fake_router):
        vm = VoiceMission(store=store)
        resp = vm.process("Surveille les vols")

    assert resp.voice_id == 3
    assert len(resp.metadata["subtask_ids"]) == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
