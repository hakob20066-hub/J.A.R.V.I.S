"""Tests KaliRunner Phase 7.6 (mocked subprocess)."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.kali_runner import KaliRunner, KaliResult


def test_detect_returns_string():
    runner = KaliRunner()
    assert runner.backend in ("wsl_kali", "wsl_ubuntu", "native", "docker", "none")


def test_status_includes_backend():
    runner = KaliRunner()
    s = runner.status()
    assert "backend" in s
    assert "available" in s


def test_run_returns_failure_when_no_backend():
    runner = KaliRunner()
    runner.backend = "none"
    result = asyncio.run(runner.run(["echo", "x"]))
    assert result.success is False
    assert "no kali backend" in (result.error or "").lower()


def test_is_tool_available_caches():
    runner = KaliRunner()
    runner.backend = "none"
    assert runner.is_tool_available("sherlock") is False
    # Cached
    assert "sherlock" in runner._tool_cache


def test_wrap_native():
    runner = KaliRunner()
    runner.backend = "native"
    wrapped = runner._wrap(["sherlock", "user"])
    assert wrapped == ["sherlock", "user"]


def test_wrap_wsl_kali():
    runner = KaliRunner()
    runner.backend = "wsl_kali"
    runner.distro_name = "kali-linux"
    wrapped = runner._wrap(["sherlock", "user"])
    assert wrapped == ["wsl", "-d", "kali-linux", "--", "sherlock", "user"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
