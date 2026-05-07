"""Tests Session 3 : SpiderFoot + recon-ng + 15 wrappers Kali."""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Trigger imports → auto-registration
import agent.osint.connectors.kali  # noqa
import agent.osint.spiderfoot_client  # noqa
import agent.osint.reconng_client  # noqa

from agent.osint.connectors import get_registry
from agent.osint.target import TargetNormalizer, TargetType, Target
from agent.osint.kali_runner import KaliResult


SESSION3_NEW = {
    "spiderfoot", "recon-ng",
    "gitleaks", "trufflehog", "zsteg", "steghide", "fierce",
    "ffuf", "gobuster", "dirsearch",
    "twint", "osintgram", "phoneinfoga", "nuclei",
    "linkedin2username", "dnsrecon",
}


# ---------- Registration tests ----------

def test_session3_all_registered():
    names = {c.name for c in get_registry().all()}
    missing = SESSION3_NEW - names
    assert not missing, f"Session 3 missing: {missing}"


def test_total_count_at_least_36():
    assert len(get_registry().all()) >= 36


def test_every_session3_has_supports():
    for name in SESSION3_NEW:
        c = get_registry().get(name)
        assert c is not None and len(c.supports) >= 1, name


# ---------- Type support sanity ----------

def test_phoneinfoga_supports_phone():
    c = get_registry().get("phoneinfoga")
    assert c.supports == {TargetType.PHONE}


def test_zsteg_steghide_image_only():
    assert get_registry().get("zsteg").supports == {TargetType.IMAGE}
    assert get_registry().get("steghide").supports == {TargetType.IMAGE}


def test_ffuf_gobuster_dirsearch_domain():
    for n in ("ffuf", "gobuster", "dirsearch"):
        assert TargetType.DOMAIN in get_registry().get(n).supports


def test_linkedin2username_person_only():
    c = get_registry().get("linkedin2username")
    assert c.supports == {TargetType.PERSON_FULL}


def test_spiderfoot_supports_many():
    c = get_registry().get("spiderfoot")
    assert TargetType.EMAIL in c.supports
    assert TargetType.DOMAIN in c.supports
    assert TargetType.IP in c.supports


# ---------- Parsing tests with mocked subprocess ----------

def _mock_runner(stdout: str, success: bool = True, returncode: int = 0,
                 stderr: str = "") -> MagicMock:
    fake = MagicMock()
    fake.is_tool_available.return_value = True

    async def fake_run(*a, **kw):
        return KaliResult(success=success, stdout=stdout, stderr=stderr,
                          returncode=returncode, elapsed_ms=10)
    fake.run = fake_run
    return fake


def test_phoneinfoga_parses_info():
    target = Target(raw="+33612345678", type=TargetType.PHONE,
                    normalized="+33612345678")
    c = get_registry().get("phoneinfoga")
    fake_stdout = (
        "Country: France\n"
        "Carrier: Orange\n"
        "Line type: mobile\n"
    )
    runner = _mock_runner(fake_stdout)
    with patch("agent.osint.connectors.kali.phoneinfoga.get_runner",
               return_value=runner):
        result = asyncio.run(c.query(target))
    assert result.success
    assert len(result.findings) == 1
    f = result.findings[0]
    assert "country" in f.extracted
    assert f.extracted["country"] == "France"


def test_nuclei_parses_jsonl():
    target = TargetNormalizer.detect("example.com")
    c = get_registry().get("nuclei")
    line1 = json.dumps({"template-id": "tech-detect",
                        "info": {"name": "Tech detect", "severity": "info",
                                 "tags": ["tech"]},
                        "matched-at": "https://example.com"})
    runner = _mock_runner(line1 + "\n")
    with patch("agent.osint.connectors.kali.nuclei.get_runner", return_value=runner):
        result = asyncio.run(c.query(target))
    assert result.success
    assert len(result.findings) == 1
    assert result.findings[0].extracted["template"] == "tech-detect"


def test_twint_parses_tweets():
    target = TargetNormalizer.detect("@fatihmakes")
    target.type = TargetType.SOCIAL_HANDLE  # forced
    c = get_registry().get("twint")
    tweet = json.dumps({"link": "https://twitter.com/x/status/1",
                        "tweet": "Hello world", "date": "2024-01-15",
                        "language": "en", "place": "Paris",
                        "mentions": [], "hashtags": []})
    fake = MagicMock()
    fake.is_tool_available.return_value = True

    async def fake_run(cmd, **kw):
        # 1er call = twint, 2e call = cat
        if "cat" in cmd:
            return KaliResult(True, tweet + "\n", "", 0, 5)
        return KaliResult(True, "", "", 0, 100)
    fake.run = fake_run
    with patch("agent.osint.connectors.kali.twint.get_runner", return_value=fake):
        result = asyncio.run(c.query(target))
    assert result.success
    assert len(result.findings) == 1
    assert result.findings[0].extracted["tweet"] == "Hello world"


def test_linkedin2username_fallback_variations():
    target = Target(raw="Fatih Makes", type=TargetType.PERSON_FULL,
                    normalized="Fatih Makes")
    c = get_registry().get("linkedin2username")
    runner = _mock_runner("", success=False)
    with patch("agent.osint.connectors.kali.linkedin2username.get_runner",
               return_value=runner):
        result = asyncio.run(c.query(target))
    assert result.success
    assert len(result.findings) >= 5
    # Vérif quelques variations classiques
    extracted_vars = {f.extracted["variation"] for f in result.findings}
    assert "fatihmakes" in extracted_vars
    assert "fatih.makes" in extracted_vars


def test_gitleaks_requires_github_url():
    target = TargetNormalizer.detect("example.com")
    c = get_registry().get("gitleaks")
    runner = _mock_runner("")
    with patch("agent.osint.connectors.kali.gitleaks.get_runner",
               return_value=runner):
        result = asyncio.run(c.query(target))
    assert result.success is False
    assert "github" in (result.error or "").lower()


def test_zsteg_skips_jpg():
    target = Target(raw="x.jpg", type=TargetType.IMAGE, normalized="/tmp/x.jpg")
    c = get_registry().get("zsteg")
    runner = _mock_runner("")
    with patch("agent.osint.connectors.kali.zsteg.get_runner", return_value=runner):
        result = asyncio.run(c.query(target))
    assert result.success is False
    assert "png" in (result.error or "").lower()


def test_steghide_skips_png():
    target = Target(raw="x.png", type=TargetType.IMAGE, normalized="/tmp/x.png")
    c = get_registry().get("steghide")
    runner = _mock_runner("")
    with patch("agent.osint.connectors.kali.steghide.get_runner", return_value=runner):
        result = asyncio.run(c.query(target))
    assert result.success is False
    assert "jpg" in (result.error or "").lower()


# ---------- SpiderFoot client ----------

def test_spiderfoot_client_dead_returns_empty():
    from agent.osint.spiderfoot_client import SpiderFootClient
    client = SpiderFootClient()
    # _is_alive() falls through to except, returns False
    target = TargetNormalizer.detect("example.com")
    with patch.object(client, "_is_alive", return_value=False), \
         patch.object(client, "_ensure_running", new=lambda: _async_false()):
        events = asyncio.run(client.scan(target))
    assert events == []


async def _async_false():
    return False


def test_spiderfoot_connector_unavailable_when_no_kali():
    from agent.osint.spiderfoot_client import SpiderFootConnector
    c = SpiderFootConnector()
    runner = MagicMock()
    runner.is_tool_available.return_value = False
    with patch("agent.osint.spiderfoot_client.get_runner", return_value=runner):
        assert c.is_available() is False


# ---------- Recon-ng client ----------

def test_reconng_build_rc_format():
    from agent.osint.reconng_client import ReconNgClient
    client = ReconNgClient()
    rc = client._build_rc(["recon/domains-hosts/builtwith"], {"DOMAIN": "example.com"})
    assert "modules load recon/domains-hosts/builtwith" in rc
    assert "options set DOMAIN example.com" in rc
    assert rc.endswith("exit")


def test_reconng_parse_stdout_extracts_rows():
    from agent.osint.reconng_client import ReconNgClient
    stdout = (
        "[*] Loading module recon/domains-hosts/builtwith\n"
        "[*] [host] sub.example.com => 1.2.3.4\n"
        "[*] [host] api.example.com => 5.6.7.8\n"
        "[*] Module finished\n"
    )
    rows = ReconNgClient._parse_stdout(stdout)
    assert len(rows) == 2
    assert rows[0]["key"] == "[host] sub.example.com"
    assert rows[0]["value"] == "1.2.3.4"


def test_reconng_connector_unavailable_when_no_kali():
    from agent.osint.reconng_client import ReconNgConnector
    c = ReconNgConnector()
    runner = MagicMock()
    runner.is_tool_available.return_value = False
    with patch("agent.osint.reconng_client.get_runner", return_value=runner):
        assert c.is_available() is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
