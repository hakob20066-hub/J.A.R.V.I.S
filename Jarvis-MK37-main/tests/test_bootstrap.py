"""Tests pour agent/bootstrap.py."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import bootstrap as bs  # noqa: E402


def _patch_paths(tmp: Path):
    """Helper : patche les chemins de bootstrap pour pointer vers tmp."""
    return patch.multiple(
        "agent.bootstrap",
        BASE_DIR=tmp,
        CONFIG_DIR=tmp / "config",
        RUNTIME_PATH=tmp / "config" / "runtime.json",
        API_KEYS_PATH=tmp / "config" / "api_keys.json",
    )


def test_bootstrap_first_launch_no_keys():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        with _patch_paths(tmp):
            result = bs.bootstrap(skip_warmup=True)
            assert result["status"] == "first_launch"
            assert result["needs_wizard"] is True


def test_bootstrap_configured_with_groq():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        cfg = tmp / "config"
        cfg.mkdir()
        (cfg / "api_keys.json").write_text(
            json.dumps({"groq_api_key": "gsk_test123"}), encoding="utf-8"
        )
        (cfg / "runtime.json").write_text(
            json.dumps({"first_launch_done": True}), encoding="utf-8"
        )
        with _patch_paths(tmp):
            result = bs.bootstrap(skip_warmup=True)
            assert result["status"] == "configured"
            assert result["needs_wizard"] is False


def test_bootstrap_local_only_mode():
    """First launch done, no cloud keys, but ollama configured → local_only."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        cfg = tmp / "config"
        cfg.mkdir()
        (cfg / "api_keys.json").write_text(
            json.dumps({"ollama_base_url": "http://localhost:11434"}),
            encoding="utf-8",
        )
        (cfg / "runtime.json").write_text(
            json.dumps({"first_launch_done": True}), encoding="utf-8"
        )
        with _patch_paths(tmp):
            result = bs.bootstrap(skip_warmup=True)
            assert result["status"] == "local_only"
            assert result["needs_wizard"] is False
            assert any("100% local" in w for w in result["warnings"])


def test_bootstrap_incomplete_after_first_launch():
    """First launch marqué done MAIS aucune clé du tout → incomplete."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        cfg = tmp / "config"
        cfg.mkdir()
        (cfg / "runtime.json").write_text(
            json.dumps({"first_launch_done": True}), encoding="utf-8"
        )
        # api_keys.json absent
        with _patch_paths(tmp):
            result = bs.bootstrap(skip_warmup=True)
            assert result["status"] == "incomplete"
            assert result["needs_wizard"] is True


def test_has_minimum_keys_skips_placeholders():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        cfg = tmp / "config"
        cfg.mkdir()
        (cfg / "api_keys.json").write_text(
            json.dumps({
                "gemini_api_key": "YOUR_GEMINI_API_KEY",  # placeholder
                "groq_api_key":   "",                      # vide
            }),
            encoding="utf-8",
        )
        with _patch_paths(tmp):
            assert bs.has_minimum_keys() is False


def test_has_minimum_keys_accepts_valid():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        cfg = tmp / "config"
        cfg.mkdir()
        (cfg / "api_keys.json").write_text(
            json.dumps({"anthropic_api_key": "sk-ant-real-key"}),
            encoding="utf-8",
        )
        with _patch_paths(tmp):
            assert bs.has_minimum_keys() is True


def test_mark_first_launch_done_persists():
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        with _patch_paths(tmp):
            bs.mark_first_launch_done()
            data = json.loads((tmp / "config" / "runtime.json").read_text())
            assert data["first_launch_done"] is True
            assert "first_launch_at" in data


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
