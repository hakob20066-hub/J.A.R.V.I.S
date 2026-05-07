"""
Tests Session 5 OSINT — 15 connecteurs Python + reporter HTML.

Couvre :
  - virustotal_py, urlscan_py, abuseipdb_py, hunter_io, github_py
  - dehashed_py, otx_py, bgpview_py, securitytrails_py, leakcheck_py
  - numverify_py, fullcontact_py, pulsedive_py, censys_py, builtwith_py
  - reporter.py (HTML render, fallback, JSON)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.connectors.base import Finding
from agent.osint.target import Target, TargetType


def _target(raw: str, ttype: TargetType = TargetType.DOMAIN) -> Target:
    return Target(raw=raw, type=ttype, normalized=raw)


def _mock_get(data, status=200, ok=True):
    async def _fake(*a, **kw):
        return {"ok": ok, "status": status, "data": data, "elapsed_ms": 10}
    return _fake


# ─────────────────────────────────────────────────────────────────────────────
# virustotal_py
# ─────────────────────────────────────────────────────────────────────────────

def test_vt_no_key():
    from agent.osint.connectors.python.virustotal_py import VirusTotalConnector
    t = _target("evil.com")
    result = asyncio.run(VirusTotalConnector().query(t))
    assert not result.success
    assert "VT_API_KEY" in (result.error or "")


def test_vt_domain_success():
    from agent.osint.connectors.python import virustotal_py
    data = {"data": {"attributes": {
        "last_analysis_stats": {"malicious": 3, "suspicious": 1, "harmless": 60, "undetected": 5},
        "reputation": -5, "categories": {"cat1": "malware"}, "tags": ["phishing"],
        "registrar": "GoDaddy", "last_analysis_date": "2024-01-01",
    }}}
    t = _target("evil.com")
    with patch.dict("os.environ", {"VT_API_KEY": "testkey"}), \
         patch("agent.osint.connectors.python.virustotal_py.async_get", _mock_get(data)):
        result = asyncio.run(virustotal_py.VirusTotalConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["malicious"] == 3


def test_vt_404():
    from agent.osint.connectors.python import virustotal_py
    t = _target("1.2.3.4", TargetType.IP)
    with patch.dict("os.environ", {"VT_API_KEY": "k"}), \
         patch("agent.osint.connectors.python.virustotal_py.async_get",
               _mock_get("", status=404, ok=False)):
        result = asyncio.run(virustotal_py.VirusTotalConnector().query(t))
    assert result.success and result.findings == []


# ─────────────────────────────────────────────────────────────────────────────
# urlscan_py
# ─────────────────────────────────────────────────────────────────────────────

def test_urlscan_parses():
    from agent.osint.connectors.python.urlscan_py import UrlScanConnector
    data = {"results": [
        {"page": {"url": "https://example.com", "ip": "1.2.3.4", "country": "US",
                  "server": "nginx", "title": "Example"},
         "stats": {"malicious": 0},
         "task": {"time": "2024-01-01T00:00:00"},
         "result": "https://urlscan.io/result/abc123/",
         "screenshot": "https://urlscan.io/screenshots/abc123.png"},
    ]}
    t = _target("example.com")
    with patch("agent.osint.connectors.python.urlscan_py.async_get", _mock_get(data)):
        result = asyncio.run(UrlScanConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["ip"] == "1.2.3.4"


def test_urlscan_empty():
    from agent.osint.connectors.python.urlscan_py import UrlScanConnector
    t = _target("newdomain.io")
    with patch("agent.osint.connectors.python.urlscan_py.async_get", _mock_get({"results": []})):
        result = asyncio.run(UrlScanConnector().query(t))
    assert result.success and result.findings == []


# ─────────────────────────────────────────────────────────────────────────────
# abuseipdb_py
# ─────────────────────────────────────────────────────────────────────────────

def test_abuseipdb_no_key():
    from agent.osint.connectors.python.abuseipdb_py import AbuseIPDBConnector
    t = _target("1.2.3.4", TargetType.IP)
    result = asyncio.run(AbuseIPDBConnector().query(t))
    assert not result.success and "ABUSEIPDB_KEY" in (result.error or "")


def test_abuseipdb_success():
    from agent.osint.connectors.python import abuseipdb_py
    data = {"data": {
        "abuseConfidenceScore": 87, "totalReports": 42, "numDistinctUsers": 12,
        "lastReportedAt": "2024-01-15T10:00:00+00:00", "countryCode": "RU",
        "isp": "Some ISP", "domain": "bad.ru", "isTor": False, "isPublic": True,
        "usageType": "Data Center/Web Hosting/Transit",
    }}
    t = _target("5.5.5.5", TargetType.IP)
    with patch.dict("os.environ", {"ABUSEIPDB_KEY": "key"}), \
         patch("agent.osint.connectors.python.abuseipdb_py.async_get", _mock_get(data)):
        result = asyncio.run(abuseipdb_py.AbuseIPDBConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["abuse_score"] == 87


# ─────────────────────────────────────────────────────────────────────────────
# hunter_io
# ─────────────────────────────────────────────────────────────────────────────

def test_hunter_no_key():
    from agent.osint.connectors.python.hunter_io import HunterIOConnector
    t = _target("company.com")
    result = asyncio.run(HunterIOConnector().query(t))
    assert not result.success and "HUNTER_KEY" in (result.error or "")


def test_hunter_success():
    from agent.osint.connectors.python import hunter_io
    data = {"data": {
        "organization": "Acme Corp", "pattern": "{first}.{last}",
        "webmail": False, "disposable": False, "accept_all": False,
        "emails": [
            {"value": "john.doe@company.com", "first_name": "John", "last_name": "Doe",
             "position": "CTO", "confidence": 92, "linkedin": "", "sources": []},
        ],
    }}
    t = _target("company.com")
    with patch.dict("os.environ", {"HUNTER_KEY": "k"}), \
         patch("agent.osint.connectors.python.hunter_io.async_get", _mock_get(data)):
        result = asyncio.run(hunter_io.HunterIOConnector().query(t))
    assert result.success
    emails = [f for f in result.findings if f.type == "email_discovered"]
    assert emails[0].extracted["email"] == "john.doe@company.com"


# ─────────────────────────────────────────────────────────────────────────────
# github_py
# ─────────────────────────────────────────────────────────────────────────────

def test_github_not_found():
    from agent.osint.connectors.python.github_py import GitHubConnector
    t = _target("nonexistent_xyz_99", TargetType.USERNAME)
    with patch("agent.osint.connectors.python.github_py.async_get",
               _mock_get("Not Found", status=404, ok=False)):
        result = asyncio.run(GitHubConnector().query(t))
    assert result.success and result.findings == []


def test_github_profile():
    from agent.osint.connectors.python import github_py
    user_data = {
        "login": "johndoe", "name": "John Doe", "email": "john@example.com",
        "bio": "Developer", "company": "Acme", "location": "Paris",
        "blog": "https://john.dev", "twitter_username": "jdoe",
        "public_repos": 42, "public_gists": 5, "followers": 100, "following": 50,
        "created_at": "2015-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        "avatar_url": "https://avatars.github.com/1", "html_url": "https://github.com/johndoe",
    }
    repos_data = [
        {"name": "myrepo", "description": "A repo", "language": "Python",
         "stargazers_count": 50, "forks_count": 10, "updated_at": "2024-01-01T00:00:00Z",
         "topics": ["python", "osint"], "html_url": "https://github.com/johndoe/myrepo"},
    ]
    call_count = 0
    async def mock_get(url, **kw):
        nonlocal call_count
        call_count += 1
        if "repos" in url:
            return {"ok": True, "status": 200, "data": repos_data, "elapsed_ms": 5}
        return {"ok": True, "status": 200, "data": user_data, "elapsed_ms": 5}

    t = _target("johndoe", TargetType.USERNAME)
    with patch("agent.osint.connectors.python.github_py.async_get", mock_get):
        result = asyncio.run(github_py.GitHubConnector().query(t))
    assert result.success
    profile = next(f for f in result.findings if f.type == "account")
    assert profile.extracted["followers"] == 100
    repos = [f for f in result.findings if f.type == "github_repo"]
    assert repos[0].extracted["repo"] == "myrepo"


# ─────────────────────────────────────────────────────────────────────────────
# dehashed_py
# ─────────────────────────────────────────────────────────────────────────────

def test_dehashed_no_creds():
    from agent.osint.connectors.python.dehashed_py import DehashedConnector
    c = DehashedConnector()
    assert not c.is_available()
    t = _target("user@test.com", TargetType.EMAIL)
    result = asyncio.run(c.query(t))
    assert not result.success


def test_dehashed_success():
    from agent.osint.connectors.python import dehashed_py
    data = {"entries": [
        {"email": "user@test.com", "username": "user123", "password": "pass123",
         "hashed_password": "", "name": "John", "database_name": "FakeDB",
         "address": "", "phone": "", "ip_address": ""},
    ], "balance": 99}
    t = _target("user@test.com", TargetType.EMAIL)
    with patch.dict("os.environ", {"DEHASHED_EMAIL": "me@me.com", "DEHASHED_KEY": "k"}), \
         patch("agent.osint.connectors.python.dehashed_py.async_get", _mock_get(data)):
        result = asyncio.run(dehashed_py.DehashedConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["database"] == "FakeDB"


# ─────────────────────────────────────────────────────────────────────────────
# otx_py
# ─────────────────────────────────────────────────────────────────────────────

def test_otx_domain():
    from agent.osint.connectors.python import otx_py
    data = {
        "pulse_info": {"count": 5, "pulses": [{"name": "Malware Campaign"}]},
        "malware": [], "url_list": [], "reputation": -3,
        "country_name": "Russia", "asn": "AS12345", "city": "Moscow",
    }
    t = _target("evil.ru")
    with patch("agent.osint.connectors.python.otx_py.async_get", _mock_get(data)):
        result = asyncio.run(otx_py.OTXConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["pulse_count"] == 5


def test_otx_empty():
    from agent.osint.connectors.python.otx_py import OTXConnector
    t = _target("clean.org")
    with patch("agent.osint.connectors.python.otx_py.async_get",
               _mock_get({"pulse_info": {"count": 0, "pulses": []},
                          "malware": [], "url_list": [], "reputation": 0})):
        result = asyncio.run(OTXConnector().query(t))
    assert result.success


# ─────────────────────────────────────────────────────────────────────────────
# bgpview_py
# ─────────────────────────────────────────────────────────────────────────────

def test_bgpview_prefixes():
    from agent.osint.connectors.python import bgpview_py
    data = {"status": "ok", "data": {
        "prefixes": [
            {"prefix": "1.2.3.0/24",
             "asn": {"asn": 1234, "name": "ACME-NET", "country_code": "US",
                     "description": "Acme Corp"},
             "name": "ACME-1", "rir_allocation": {"rir_name": "ARIN"}},
        ],
    }}
    t = _target("1.2.3.4", TargetType.IP)
    with patch("agent.osint.connectors.python.bgpview_py.async_get", _mock_get(data)):
        result = asyncio.run(bgpview_py.BGPViewConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["asn"] == 1234
    assert result.findings[0].extracted["prefix"] == "1.2.3.0/24"


def test_bgpview_empty_falls_back_rir():
    from agent.osint.connectors.python import bgpview_py
    data = {"status": "ok", "data": {
        "prefixes": [],
        "rir_allocation": {"rir_name": "RIPE", "prefix": "1.0.0.0/8",
                           "date_allocated": "2000-01-01"},
    }}
    t = _target("1.0.0.1", TargetType.IP)
    with patch("agent.osint.connectors.python.bgpview_py.async_get", _mock_get(data)):
        result = asyncio.run(bgpview_py.BGPViewConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["rir"] == "RIPE"


# ─────────────────────────────────────────────────────────────────────────────
# securitytrails_py
# ─────────────────────────────────────────────────────────────────────────────

def test_securitytrails_no_key():
    from agent.osint.connectors.python.securitytrails_py import SecurityTrailsConnector
    t = _target("example.com")
    result = asyncio.run(SecurityTrailsConnector().query(t))
    assert not result.success and "ST_API_KEY" in (result.error or "")


def test_securitytrails_subdomains():
    from agent.osint.connectors.python import securitytrails_py

    sub_data   = {"subdomains": ["api", "mail", "dev"], "meta": {"total_pages": 1}}
    dns_data   = {"records": [
        {"first_seen": "2020-01-01", "last_seen": "2024-01-01",
         "values": [{"ip": "1.2.3.4"}]},
    ]}

    async def mock_gather(*coros):
        return [
            {"ok": True, "status": 200, "data": sub_data, "elapsed_ms": 5},
            {"ok": True, "status": 200, "data": dns_data, "elapsed_ms": 5},
        ]

    t = _target("example.com")
    with patch.dict("os.environ", {"ST_API_KEY": "k"}), \
         patch("asyncio.gather", mock_gather):
        result = asyncio.run(securitytrails_py.SecurityTrailsConnector().query(t))
    assert result.success
    subs = [f for f in result.findings if f.type == "subdomain"]
    assert any("api.example.com" in f.extracted["subdomain"] for f in subs)


# ─────────────────────────────────────────────────────────────────────────────
# leakcheck_py
# ─────────────────────────────────────────────────────────────────────────────

def test_leakcheck_no_key():
    from agent.osint.connectors.python.leakcheck_py import LeakCheckConnector
    t = _target("a@b.com", TargetType.EMAIL)
    result = asyncio.run(LeakCheckConnector().query(t))
    assert not result.success


def test_leakcheck_found():
    from agent.osint.connectors.python import leakcheck_py
    data = {"success": True, "sources": [
        {"name": "LeakedDB2023", "breach_date": "2023-01-01",
         "leak_type": "Combo", "fields": ["email", "password"]},
    ]}
    t = _target("victim@test.com", TargetType.EMAIL)
    with patch.dict("os.environ", {"LEAKCHECK_KEY": "k"}), \
         patch("agent.osint.connectors.python.leakcheck_py.async_get", _mock_get(data)):
        result = asyncio.run(leakcheck_py.LeakCheckConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["leak_name"] == "LeakedDB2023"


# ─────────────────────────────────────────────────────────────────────────────
# numverify_py
# ─────────────────────────────────────────────────────────────────────────────

def test_numverify_no_key():
    from agent.osint.connectors.python.numverify_py import NumverifyConnector
    t = _target("+33612345678", TargetType.PHONE)
    result = asyncio.run(NumverifyConnector().query(t))
    assert not result.success


def test_numverify_valid_phone():
    from agent.osint.connectors.python import numverify_py
    data = {
        "valid": True, "number": "33612345678",
        "local_format": "0612345678", "international_format": "+33612345678",
        "country_prefix": "+33", "country_code": "FR", "country_name": "France",
        "location": "Paris", "carrier": "Orange", "line_type": "mobile",
    }
    t = _target("+33612345678", TargetType.PHONE)
    with patch.dict("os.environ", {"NUMVERIFY_KEY": "k"}), \
         patch("agent.osint.connectors.python.numverify_py.async_get", _mock_get(data)):
        result = asyncio.run(numverify_py.NumverifyConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["carrier"] == "Orange"
    assert result.findings[0].extracted["line_type"] == "mobile"


# ─────────────────────────────────────────────────────────────────────────────
# fullcontact_py
# ─────────────────────────────────────────────────────────────────────────────

def test_fullcontact_no_key():
    from agent.osint.connectors.python.fullcontact_py import FullContactConnector
    t = _target("user@example.com", TargetType.EMAIL)
    result = asyncio.run(FullContactConnector().query(t))
    assert not result.success and "FC_API_KEY" in (result.error or "")


def test_fullcontact_success():
    from agent.osint.connectors.python import fullcontact_py

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = {
        "fullName": "Alice Smith", "ageRange": "25-34", "gender": "Female",
        "location": "Paris, France", "bio": "Engineer",
        "avatar": "https://cdn.example.com/avatar.jpg",
        "socialProfiles": [{"type": "linkedin", "url": "https://linkedin.com/in/alice"}],
        "employment": [{"name": "Acme Corp"}],
        "education": [{"name": "MIT"}],
    }

    t = _target("alice@example.com", TargetType.EMAIL)
    with patch.dict("os.environ", {"FC_API_KEY": "k"}):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client
            result = asyncio.run(fullcontact_py.FullContactConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["full_name"] == "Alice Smith"
    assert result.findings[0].extracted["linkedin"] == "https://linkedin.com/in/alice"


# ─────────────────────────────────────────────────────────────────────────────
# pulsedive_py
# ─────────────────────────────────────────────────────────────────────────────

def test_pulsedive_domain():
    from agent.osint.connectors.python import pulsedive_py
    data = {
        "iid": 123, "indicator": "evil.com", "type": "domain",
        "risk": "high", "risk_recommended": "high",
        "threats": [{"name": "MalCampaign"}], "feeds": [{"name": "AlienVault"}],
        "attributes": {"port": [80, 443]},
        "stamp_added": "2022-01-01 00:00:00", "stamp_seen": "2024-01-01 00:00:00",
        "seen": 15,
    }
    t = _target("evil.com")
    with patch("agent.osint.connectors.python.pulsedive_py.async_get", _mock_get(data)):
        result = asyncio.run(pulsedive_py.PulsediveConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["risk"] == "high"
    assert "MalCampaign" in result.findings[0].extracted["threats"]


def test_pulsedive_unknown():
    from agent.osint.connectors.python import pulsedive_py
    t = _target("clean.io")
    with patch("agent.osint.connectors.python.pulsedive_py.async_get",
               _mock_get({"error": "not found"}, ok=True)):
        result = asyncio.run(pulsedive_py.PulsediveConnector().query(t))
    assert result.success and result.findings == []


# ─────────────────────────────────────────────────────────────────────────────
# censys_py
# ─────────────────────────────────────────────────────────────────────────────

def test_censys_no_creds():
    from agent.osint.connectors.python.censys_py import CensysConnector
    c = CensysConnector()
    assert not c.is_available()
    t = _target("1.2.3.4", TargetType.IP)
    result = asyncio.run(c.query(t))
    assert not result.success


def test_censys_success():
    from agent.osint.connectors.python import censys_py
    data = {"result": {
        "ip": "1.2.3.4",
        "autonomous_system": {"name": "Cloudflare", "asn": 13335},
        "location": {"country": "US", "city": "San Francisco",
                     "coordinates": {"latitude": 37.7, "longitude": -122.4}},
        "last_updated_at": "2024-01-01T00:00:00Z",
        "services": [
            {"port": 80, "transport_protocol": "TCP", "service_name": "HTTP",
             "extended_service_name": "NGINX", "certificate": ""},
            {"port": 443, "transport_protocol": "TCP", "service_name": "HTTPS",
             "extended_service_name": "NGINX", "certificate": "abc123"},
        ],
    }}
    t = _target("1.2.3.4", TargetType.IP)
    with patch.dict("os.environ", {"CENSYS_API_ID": "uid", "CENSYS_API_SECRET": "sec"}), \
         patch("agent.osint.connectors.python.censys_py.async_get", _mock_get(data)):
        result = asyncio.run(censys_py.CensysConnector().query(t))
    assert result.success
    host = next(f for f in result.findings if f.type == "host_info")
    assert host.extracted["autonomous_system"] == "Cloudflare"
    ports = [f for f in result.findings if f.type == "open_port"]
    assert any(p.extracted["port"] == 443 for p in ports)


# ─────────────────────────────────────────────────────────────────────────────
# builtwith_py
# ─────────────────────────────────────────────────────────────────────────────

def test_builtwith_no_key():
    from agent.osint.connectors.python.builtwith_py import BuiltWithConnector
    t = _target("example.com")
    result = asyncio.run(BuiltWithConnector().query(t))
    assert not result.success


def test_builtwith_tech_stack():
    from agent.osint.connectors.python import builtwith_py
    data = {"Results": [
        {"Result": {"Paths": [
            {"Technologies": [
                {"Name": "WordPress", "Categories": ["CMS"]},
                {"Name": "jQuery", "Categories": ["JavaScript Frameworks"]},
                {"Name": "Cloudflare", "Categories": ["CDN"]},
            ]},
        ]}},
    ]}
    t = _target("blog.example.com")
    with patch.dict("os.environ", {"BW_API_KEY": "k"}), \
         patch("agent.osint.connectors.python.builtwith_py.async_get", _mock_get(data)):
        result = asyncio.run(builtwith_py.BuiltWithConnector().query(t))
    assert result.success
    techs = result.findings[0].extracted["technologies"]
    assert "WordPress" in techs and "jQuery" in techs
    assert "CMS" in result.findings[0].extracted["categories"]


# ─────────────────────────────────────────────────────────────────────────────
# REPORTER
# ─────────────────────────────────────────────────────────────────────────────

def _make_report():
    """Construit un OSINTReport minimal pour les tests reporter."""
    from agent.osint.engine import OSINTReport
    from agent.osint.target import TargetNormalizer
    t = TargetNormalizer.detect("example.com")
    r = OSINTReport(
        target=t, mode="self_audit",
        started_at=time.time() - 5, completed_at=time.time(),
        findings=[
            Finding(type="subdomain", source="crtsh",
                    extracted={"subdomain": "api.example.com"}, confidence=0.9),
            Finding(type="whois", source="whois_py",
                    extracted={"registrar": "GoDaddy"}, confidence=0.85),
        ],
        sources_used=["crtsh", "whois_py"],
        sources_failed=[("hibp", "rate limited")],
        analyzers={
            "behavior": {"language": "en", "topics": ["python"], "posts_per_day": 0.0,
                         "weekday_ratio": 0.0, "most_active_hour": None, "timezone": None,
                         "language_scores": {}, "sample_count": 0},
            "network": {"nodes": [], "edges": [], "co_mentions": {},
                        "geo_clusters": [], "triangulations": []},
            "historical": {"events": [], "earliest": None, "latest": None,
                           "wayback_count": 0, "archives_count": 0, "total_events": 0},
            "metadata": {"gps_points": [], "devices": {}, "software": {},
                         "creators": {}, "stega_signals": [], "serial_reuse": []},
        },
    )
    return r


def test_reporter_jinja_available():
    from agent.osint.reporter import _HAS_JINJA
    assert _HAS_JINJA, "jinja2 doit être installé (pip install jinja2)"


def test_reporter_renders_html(tmp_path):
    from agent.osint.reporter import OSINTReporter
    r = _make_report()
    reporter = OSINTReporter()
    html_path = reporter.build(r, output_dir=tmp_path)
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")
    assert "example.com" in content
    assert "crtsh" in content
    assert "GoDaddy" in content
    assert "subdomain" in content


def test_reporter_writes_json(tmp_path):
    from agent.osint.reporter import OSINTReporter
    r = _make_report()
    OSINTReporter().build(r, output_dir=tmp_path)
    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["mode"] == "self_audit"
    assert data["findings_count"] == 2


def test_reporter_fallback_html(tmp_path):
    from agent.osint.reporter import OSINTReporter
    import agent.osint.reporter as rep_mod
    orig = rep_mod._HAS_JINJA
    rep_mod._HAS_JINJA = False
    try:
        r = _make_report()
        html_path = OSINTReporter().build(r, output_dir=tmp_path)
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "example.com" in content
    finally:
        rep_mod._HAS_JINJA = orig


def test_reporter_html_contains_analyzers(tmp_path):
    from agent.osint.reporter import OSINTReporter
    r = _make_report()
    html_path = OSINTReporter().build(r, output_dir=tmp_path)
    content = html_path.read_text(encoding="utf-8")
    assert "Analysis" in content
    assert "Behavior" in content or "behavior" in content


def test_reporter_sources_in_html(tmp_path):
    from agent.osint.reporter import OSINTReporter
    r = _make_report()
    html_path = OSINTReporter().build(r, output_dir=tmp_path)
    content = html_path.read_text(encoding="utf-8")
    assert "whois_py" in content
    assert "hibp" in content  # failed source


def test_reporter_singleton():
    from agent.osint.reporter import get_reporter, _REPORTER_SINGLETON
    r1 = get_reporter()
    r2 = get_reporter()
    assert r1 is r2


# ─────────────────────────────────────────────────────────────────────────────
# Auto-enregistrement — 25 connecteurs dans le registry
# ─────────────────────────────────────────────────────────────────────────────

def test_all_connectors_registered():
    import agent.osint.connectors.python  # noqa: F401
    from agent.osint.connectors.base import get_registry
    names = {c.name for c in get_registry().all()}
    expected_s5 = {
        "virustotal_py", "urlscan_py", "abuseipdb_py", "hunter_io", "github_py",
        "dehashed_py", "otx_py", "bgpview_py", "securitytrails_py", "leakcheck_py",
        "numverify_py", "fullcontact_py", "pulsedive_py", "censys_py", "builtwith_py",
    }
    missing = expected_s5 - names
    assert not missing, f"Connecteurs non enregistrés: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn() if "tmp_path" not in fn.__code__.co_varnames else fn(Path("_tmp_test"))
            print(f"  [OK] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
    print(f"\n[RESULTS] Session 5 OSINT -- {passed}/{passed+failed} passed"
          + (f", {failed} failed" if failed else " OK"))
