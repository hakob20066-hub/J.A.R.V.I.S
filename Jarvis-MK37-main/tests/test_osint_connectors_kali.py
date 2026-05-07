"""Tests smoke pour les 20 wrappers Kali Phase 7.6."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.connectors import get_registry
from agent.osint.connectors.base import Connector
from agent.osint.target import TargetNormalizer, TargetType
from agent.osint.kali_runner import KaliResult


# Trigger imports → auto-registration
import agent.osint.connectors.kali  # noqa


EXPECTED_CONNECTORS = {
    "sherlock", "maigret", "holehe", "theHarvester",
    "sublist3r", "subfinder", "amass",
    "whois", "dnsenum", "dig", "host", "nmap",
    "shodan_cli",
    "waybackurls", "gau", "photon", "googler",
    "exiftool", "stegseek", "instaloader",
}


def test_all_20_connectors_registered():
    registry = get_registry()
    names = {c.name for c in registry.all()}
    missing = EXPECTED_CONNECTORS - names
    assert not missing, f"Missing connectors: {missing}"


def test_each_connector_has_supports():
    registry = get_registry()
    for name in EXPECTED_CONNECTORS:
        c = registry.get(name)
        assert c is not None, name
        assert isinstance(c.supports, set), name
        assert len(c.supports) >= 1, name


def test_each_connector_backend_kali():
    registry = get_registry()
    for name in EXPECTED_CONNECTORS:
        c = registry.get(name)
        assert c.backend == "kali", f"{name} backend should be 'kali'"


def test_sherlock_supports_username_types():
    sherlock = get_registry().get("sherlock")
    assert TargetType.USERNAME in sherlock.supports
    assert TargetType.INSTAGRAM_HANDLE in sherlock.supports


def test_holehe_supports_email():
    c = get_registry().get("holehe")
    assert c.supports == {TargetType.EMAIL}


def test_exiftool_supports_image():
    c = get_registry().get("exiftool")
    assert c.supports == {TargetType.IMAGE}


def test_nmap_supports_ip_and_domain():
    c = get_registry().get("nmap")
    assert TargetType.IP in c.supports
    assert TargetType.DOMAIN in c.supports


def test_googler_supports_many_types():
    c = get_registry().get("googler")
    assert TargetType.PERSON_FULL in c.supports
    assert TargetType.EMAIL in c.supports
    assert TargetType.PHONE in c.supports


def test_connector_returns_failure_when_no_backend():
    """Si Kali backend = none, query() doit retourner success=False sans crasher."""
    target = TargetNormalizer.detect("user")
    c = get_registry().get("sherlock")

    fake_runner = MagicMock()
    fake_runner.is_tool_available.return_value = False
    fake_runner.run = MagicMock(return_value=asyncio.sleep(0))

    async def fake_run(*a, **kw):
        return KaliResult(success=False, stdout="", stderr="", returncode=-1,
                          elapsed_ms=0, error="No Kali backend available")
    fake_runner.run = fake_run

    with patch("agent.osint.connectors.kali.sherlock.get_runner", return_value=fake_runner):
        result = asyncio.run(c.query(target))
    assert result.success is False
    assert result.error is not None


def test_sherlock_parses_stdout_output():
    """Smoke parse output Sherlock fictif."""
    target = TargetNormalizer.detect("fatihmakes")
    c = get_registry().get("sherlock")

    fake_stdout = (
        "[*] Checking username fatihmakes on:\n"
        "[+] GitHub: https://github.com/fatihmakes\n"
        "[+] Twitter: https://twitter.com/fatihmakes\n"
        "[-] NotOnSite: https://notonsite.com/fatihmakes\n"
    )
    fake_runner = MagicMock()
    fake_runner.is_tool_available.return_value = True

    async def fake_run(*a, **kw):
        return KaliResult(success=True, stdout=fake_stdout, stderr="",
                          returncode=0, elapsed_ms=120)
    fake_runner.run = fake_run

    with patch("agent.osint.connectors.kali.sherlock.get_runner", return_value=fake_runner):
        result = asyncio.run(c.query(target))
    assert result.success is True
    assert len(result.findings) == 2
    assert any(f.url == "https://github.com/fatihmakes" for f in result.findings)


def test_holehe_parses_only_used():
    target = TargetNormalizer.detect("fatih@example.com")
    c = get_registry().get("holehe")
    fake_stdout = (
        "[+] adobe.com\n"
        "[+] spotify.com\n"
        "[-] linkedin.com\n"
    )
    fake_runner = MagicMock()
    fake_runner.is_tool_available.return_value = True

    async def fake_run(*a, **kw):
        return KaliResult(success=True, stdout=fake_stdout, stderr="",
                          returncode=0, elapsed_ms=300)
    fake_runner.run = fake_run

    with patch("agent.osint.connectors.kali.holehe.get_runner", return_value=fake_runner):
        result = asyncio.run(c.query(target))
    assert result.success is True
    assert len(result.findings) == 2


def test_exiftool_parses_gps_finding():
    target = TargetNormalizer.detect("/tmp/fake.jpg")
    # Patch is_image_path to bypass file existence
    target.type = TargetType.IMAGE
    c = get_registry().get("exiftool")

    fake_stdout = (
        '[{"FileName":"x.jpg","GPSLatitude":48.8566,"GPSLongitude":2.3522,'
        '"DateTimeOriginal":"2024:01:15 14:30:00","Make":"Canon","Model":"EOS R5"}]'
    )
    fake_runner = MagicMock()
    fake_runner.is_tool_available.return_value = True

    async def fake_run(*a, **kw):
        return KaliResult(success=True, stdout=fake_stdout, stderr="",
                          returncode=0, elapsed_ms=50)
    fake_runner.run = fake_run

    with patch("agent.osint.connectors.kali.exiftool.get_runner", return_value=fake_runner):
        result = asyncio.run(c.query(target))
    assert result.success is True
    # Doit y avoir 1 finding GPS + 1 finding metadata
    types = [f.type for f in result.findings]
    assert "exif_gps" in types
    assert "exif_metadata" in types
    gps = next(f for f in result.findings if f.type == "exif_gps")
    assert gps.extracted["latitude"] == 48.8566


def test_dig_runs_for_each_record_type():
    """dig wrapper interroge plusieurs types DNS."""
    target = TargetNormalizer.detect("example.com")
    c = get_registry().get("dig")

    call_count = {"n": 0}

    async def fake_run(*a, **kw):
        call_count["n"] += 1
        return KaliResult(success=True, stdout="93.184.216.34\n", stderr="",
                          returncode=0, elapsed_ms=10)

    fake_runner = MagicMock()
    fake_runner.is_tool_available.return_value = True
    fake_runner.run = fake_run

    with patch("agent.osint.connectors.kali.dig_kali.get_runner", return_value=fake_runner):
        result = asyncio.run(c.query(target))
    assert call_count["n"] == 7  # A, AAAA, MX, TXT, NS, SOA, CNAME


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
