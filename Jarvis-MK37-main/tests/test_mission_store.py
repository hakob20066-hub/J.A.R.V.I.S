"""Tests pour agent/mission_store.py + agent/mission_models.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.mission_models import Mission  # noqa: E402
from agent.mission_store import MissionStore  # noqa: E402


def _make_store() -> tuple[MissionStore, Path]:
    """Crée un store dans un répertoire temporaire (Windows-safe)."""
    tmp_dir = Path(tempfile.mkdtemp())
    path = tmp_dir / "missions.json"
    return MissionStore(path), path


def test_add_and_get():
    store, _ = _make_store()
    m = Mission(id="abc", description="test")
    assert store.add(m) is True
    assert store.get("abc").description == "test"


def test_add_duplicate_returns_false():
    store, _ = _make_store()
    store.add(Mission(id="x", description="a"))
    assert store.add(Mission(id="x", description="b")) is False
    assert store.get("x").description == "a"  # original conservé


def test_persist_across_instances():
    store, path = _make_store()
    store.add(Mission(id="persist", description="hi"))

    store2 = MissionStore(path)
    assert store2.get("persist").description == "hi"


def test_status_queries():
    store, _ = _make_store()
    store.add(Mission(id="p1", description="x", status="pending"))
    store.add(Mission(id="r1", description="x", status="running"))
    store.add(Mission(id="d1", description="x", status="done"))
    assert len(store.get_pending()) == 1
    assert len(store.get_running()) == 1
    assert len(store.get_done()) == 1


def test_claim_next_pending_marks_running():
    store, _ = _make_store()
    store.add(Mission(id="m1", description="first"))
    claimed = store.claim_next_pending()
    assert claimed is not None
    assert claimed.id == "m1"
    assert claimed.status == "running"
    # Re-claim ne retourne plus rien
    assert store.claim_next_pending() is None


def test_claim_returns_oldest_first():
    store, _ = _make_store()
    store.add(Mission(id="newer", description="x", created_at="2026-04-30T10:00:00"))
    store.add(Mission(id="older", description="x", created_at="2026-04-29T10:00:00"))
    claimed = store.claim_next_pending()
    assert claimed.id == "older"


def test_recover_orphans_cancels_running_and_pending():
    """Au boot, on n'auto-replay PAS les missions de la session précédente."""
    store, _ = _make_store()
    store.add(Mission(id="orphan_running", description="x", status="running"))
    store.add(Mission(id="orphan_pending", description="y", status="pending"))
    abandoned = store.recover_orphans()
    assert len(abandoned) == 2
    assert store.get("orphan_running").status == "cancelled"
    assert store.get("orphan_pending").status == "cancelled"
    assert "abandoned" in (store.get("orphan_running").error or "")


def test_mission_lifecycle_helpers():
    m = Mission(id="x", description="x")
    assert m.status == "pending"
    m.mark_running()
    assert m.status == "running" and m.started_at
    m.mark_done("result text")
    assert m.status == "done"
    assert m.result == "result text"
    assert m.progress == 1.0
    assert m.is_terminal()


def test_mission_failed_can_retry():
    """max_retries=2 : 1ere fail OK pour retry, 2eme fail = plus de retry."""
    m = Mission(id="x", description="x", max_retries=2)
    m.mark_failed("err1")
    assert m.can_retry()       # retry_count=1, 1 < 2 → True
    m.mark_failed("err2")
    assert not m.can_retry()   # retry_count=2, 2 < 2 → False


def test_to_from_dict_roundtrip():
    m = Mission(id="rt", description="round trip", subtask_ids=["a", "b"])
    d = m.to_dict()
    m2 = Mission.from_dict(d)
    assert m2.id == m.id
    assert m2.subtask_ids == ["a", "b"]


def test_stats():
    store, _ = _make_store()
    store.add(Mission(id="a", description="x", status="pending"))
    store.add(Mission(id="b", description="x", status="done"))
    store.add(Mission(id="c", description="x", status="done"))
    s = store.stats()
    assert s["pending"] == 1
    assert s["done"] == 2
    assert s["total"] == 3


def test_clear_done_keeps_recent():
    store, _ = _make_store()
    for i in range(10):
        store.add(Mission(
            id=f"d{i}", description="x", status="done",
            completed_at=f"2026-04-{i:02d}T10:00:00",
        ))
    deleted = store.clear_done(keep_last=3)
    assert deleted == 7
    remaining_done = store.get_done()
    assert len(remaining_done) == 3


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
