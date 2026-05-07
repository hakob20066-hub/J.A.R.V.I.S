"""Tests pour la séparation parole vs action dans agent/authority.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.authority import Authority  # noqa: E402


def _make_authority(policy: dict) -> Authority:
    """Helper : crée une Authority avec une policy injectée + audit redirigé."""
    a = Authority()
    a.policy = policy
    return a


def test_speech_only_tool_always_allowed():
    """Un tool speech-only passe quel que soit le mode."""
    a = _make_authority({
        "mode": "paranoid",  # mode le plus strict
        "speech_only_tools": ["tell_user", "query_memory"],
        "denylist": [],
        "ask_for": [],
        "allowlist": [],
    })
    verdict, reason = a.check("tell_user", {})
    assert verdict == "allow"
    assert "speech-only" in reason


def test_denylist_overrides_speech_only():
    """Sécurité : denylist a priorité absolue, même sur speech_only_tools.
    Évite qu'un tool malveillant ajouté à speech_only_tools bypass la denylist."""
    a = _make_authority({
        "mode": "balanced",
        "speech_only_tools": ["tell_user"],
        "denylist": ["tell_user"],
        "ask_for": [], "allowlist": [],
    })
    verdict, reason = a.check("tell_user", {})
    assert verdict == "deny"
    assert "denylisted" in reason


def test_action_tool_still_gated_in_paranoid():
    """Un tool d'ACTION reste gated en mode paranoid."""
    a = _make_authority({
        "mode": "paranoid",
        "speech_only_tools": ["tell_user"],
        "denylist": [], "ask_for": [], "allowlist": [],
    })
    verdict, _ = a.check("send_email", {"to": "x@y.com"})
    assert verdict == "ask"


def test_action_tool_in_denylist_blocked():
    a = _make_authority({
        "mode": "balanced",
        "speech_only_tools": [],
        "denylist": ["dangerous_tool"],
        "ask_for": [], "allowlist": [],
    })
    verdict, _ = a.check("dangerous_tool", {})
    assert verdict == "deny"


def test_action_tool_in_allowlist_passes():
    a = _make_authority({
        "mode": "balanced",
        "speech_only_tools": [],
        "denylist": [],
        "ask_for": [],
        "allowlist": ["weather_report"],
    })
    verdict, reason = a.check("weather_report", {})
    assert verdict == "allow"
    assert "allowlisted" in reason


def test_is_speech_only():
    a = _make_authority({
        "mode": "balanced",
        "speech_only_tools": ["tell_user", "query_memory"],
    })
    assert a.is_speech_only("tell_user")
    assert a.is_speech_only("query_memory")
    assert not a.is_speech_only("send_email")
    assert not a.is_speech_only("delete_file")


def test_speech_audit_level_is_speech():
    """Vérifie que les audits speech ont level='speech'."""
    a = _make_authority({
        "mode": "balanced",
        "speech_only_tools": ["tell_user"],
        "denylist": [], "ask_for": [], "allowlist": [],
    })
    captured = []
    with patch("agent.authority._audit", side_effect=captured.append):
        a.check("tell_user", {})
    assert len(captured) == 1
    assert captured[0]["level"] == "speech"


def test_action_audit_level_is_action():
    a = _make_authority({
        "mode": "balanced",
        "speech_only_tools": [],
        "denylist": [], "ask_for": [],
        "allowlist": ["weather_report"],
    })
    captured = []
    with patch("agent.authority._audit", side_effect=captured.append):
        a.check("weather_report", {})
    assert captured[-1]["level"] == "action"


def test_default_policy_has_speech_only_tools():
    """Vérifie que la policy par défaut inclut des speech-only tools."""
    from agent.authority import DEFAULT_POLICY
    assert "speech_only_tools" in DEFAULT_POLICY
    assert len(DEFAULT_POLICY["speech_only_tools"]) > 0
    # Quelques exemples qui devraient être speech-only
    assert "tell_user" in DEFAULT_POLICY["speech_only_tools"]
    assert "query_memory" in DEFAULT_POLICY["speech_only_tools"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
