"""
Tests Phase 7.5 — Safety Net :
  - audit_log persistant (JSONL)
  - demo_mode runtime flag
  - push/get/rollback action history
  - kill switch + register_kill_callback
  - emergency_stop hotkey listener (smoke seulement, pas de simulation kbd)
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_safety(tmp_path, monkeypatch):
    """Redirige AUDIT_PATH et RUNTIME_PATH vers un tmpdir, et reset les
    singletons en mémoire entre tests."""
    from agent import safety_audit as sa
    monkeypatch.setattr(sa, "AUDIT_PATH",   tmp_path / "audit.log")
    monkeypatch.setattr(sa, "RUNTIME_PATH", tmp_path / "runtime.json")
    sa.clear_history()
    with sa._KILL_LOCK:
        sa._KILL_CALLBACKS.clear()
    yield


# ───────────────────────── audit_log ─────────────────────────

def test_audit_log_writes_jsonl():
    from agent.safety_audit import audit_log, AUDIT_PATH
    audit_log("foo", {"k": "v"})
    audit_log("bar", {"x": 42})

    assert AUDIT_PATH.exists()
    lines = AUDIT_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    a = json.loads(lines[0]); b = json.loads(lines[1])
    assert a["event"] == "foo" and a["details"] == {"k": "v"}
    assert b["event"] == "bar" and b["details"] == {"x": 42}
    assert "ts" in a and "ts" in b


def test_read_recent_audit_returns_chronological_reverse():
    from agent.safety_audit import audit_log, read_recent_audit
    for i in range(5):
        audit_log("evt", {"i": i})
    recent = read_recent_audit(limit=3)
    assert len(recent) == 3
    # Les + récents en premier
    assert recent[0]["details"]["i"] == 4
    assert recent[1]["details"]["i"] == 3
    assert recent[2]["details"]["i"] == 2


def test_audit_log_never_raises_on_disk_error(monkeypatch, tmp_path):
    from agent import safety_audit as sa
    # Path en lecture seule
    monkeypatch.setattr(sa, "AUDIT_PATH", tmp_path / "ro" / "audit.log")
    # Empêche la création du parent
    (tmp_path / "ro").touch()  # crée un FICHIER là où on attend un dir
    # Doit pas lever
    sa.audit_log("x", {})


# ───────────────────────── demo_mode ─────────────────────────

def test_demo_mode_default_false():
    from agent.safety_audit import is_demo_mode
    assert is_demo_mode() is False


def test_set_demo_mode_persists_and_audits():
    from agent.safety_audit import set_demo_mode, is_demo_mode, read_recent_audit
    set_demo_mode(True, reason="test")
    assert is_demo_mode() is True
    set_demo_mode(False)
    assert is_demo_mode() is False
    events = [e["event"] for e in read_recent_audit(limit=10)]
    assert events.count("demo_toggle") == 2


# ───────────────────── action history & rollback ─────────────────────

def test_push_action_appears_in_history():
    from agent.safety_audit import push_action, get_history
    push_action("file_write", "wrote /tmp/x", undo=lambda: "restored")
    push_action("shell", "ran ls", undo=None)
    h = get_history()
    assert h[0]["name"] == "shell"  # plus récent en premier
    assert h[1]["name"] == "file_write"
    assert h[0]["rollbackable"] is False
    assert h[1]["rollbackable"] is True
    # Le callable undo n'est jamais sérialisé vers l'UI
    assert "undo" not in h[0]


def test_rollback_last_finds_most_recent_rollbackable():
    from agent.safety_audit import push_action, rollback_last, get_history
    flag = {"undone": False}

    def undo_fn():
        flag["undone"] = True
        return "ok"

    push_action("file_write", "fileA", undo=undo_fn)
    push_action("shell", "ran cmd", undo=None)  # irréversible — skip

    res = rollback_last()
    assert res["ok"] is True
    assert res["name"] == "file_write"
    assert flag["undone"] is True

    # Après rollback, l'action est marquée
    h = get_history()
    file_entry = next(e for e in h if e["name"] == "file_write")
    assert file_entry.get("rolled_back") is True


def test_rollback_when_nothing_rollbackable():
    from agent.safety_audit import push_action, rollback_last
    push_action("shell", "ran cmd", undo=None)
    res = rollback_last()
    assert res["ok"] is False
    assert "Aucune" in res["reason"] or "rollback" in res["reason"].lower()


def test_rollback_failure_is_caught():
    from agent.safety_audit import push_action, rollback_last
    def boom():
        raise RuntimeError("nope")
    push_action("file_write", "x", undo=boom)
    res = rollback_last()
    assert res["ok"] is False
    assert "rollback failed" in res["reason"]


# ───────────────────────── kill switch ─────────────────────────

def test_register_kill_callback_invoked_on_trigger():
    from agent.safety_audit import register_kill_callback, trigger_kill_switch, is_demo_mode
    calls = []
    register_kill_callback(lambda: calls.append("a"))
    register_kill_callback(lambda: calls.append("b"))
    res = trigger_kill_switch(reason="test")
    assert res["ok"] is True
    assert res["stopped"] == 2
    assert calls == ["a", "b"]
    # Effet de bord : demo_mode doit être ON
    assert is_demo_mode() is True


def test_kill_switch_isolates_callback_failures():
    from agent.safety_audit import register_kill_callback, trigger_kill_switch
    def boom():
        raise RuntimeError("fail")
    register_kill_callback(boom)
    register_kill_callback(lambda: None)
    res = trigger_kill_switch()
    assert res["ok"] is False
    assert res["stopped"] == 2
    assert len(res["errors"]) == 1


def test_kill_switch_emits_audit_events():
    from agent.safety_audit import trigger_kill_switch, read_recent_audit
    trigger_kill_switch(reason="unit-test")
    events = [e["event"] for e in read_recent_audit(limit=10)]
    assert "kill_switch" in events
    assert "demo_toggle" in events  # set_demo_mode True


# ───────────────────────── emergency_stop module ─────────────────────────

def test_emergency_stop_picks_backend_or_no_op():
    """Smoke : la lib `keyboard` est installée → backend doit être 'keyboard'.
    Pas de hotkey simulée, juste qu'on ne crash pas à l'init."""
    from agent.emergency_stop import EmergencyStopListener
    listener = EmergencyStopListener()
    assert listener._backend in ("keyboard", "pynput", "none")


# ───────────────────────── UI bridge wiring ─────────────────────────

def test_ui_html_has_safety_panel():
    html = (ROOT / "ui.html").read_text(encoding="utf-8")
    assert 'safety-panel' in html
    assert 'Safety Net' in html
    assert 'killSwitch()' in html
    assert 'rollbackLast()' in html
    assert 'toggleDemo()' in html


def test_ui_py_exposes_safety_methods():
    src = (ROOT / "ui.py").read_text(encoding="utf-8")
    for name in ("get_safety_state", "toggle_demo_mode", "trigger_kill_switch", "rollback_last_action"):
        assert f"def {name}" in src, f"_Api.{name} manquant dans ui.py"


def test_main_py_wires_safety_at_boot():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "register_kill_callback" in src
    assert "start_emergency_stop" in src
    assert 'audit_log("boot_complete"' in src
