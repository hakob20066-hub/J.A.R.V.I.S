"""
Tests Session 4 OSINT — 4 analyzers + base HTTP + 10 connecteurs Python.

Couvre :
  - BehaviorAnalyzer  (timezone, langue, topics, cadence)
  - NetworkMapper     (nodes, edges, triangulation, geo)
  - HistoricalScraper (timeline, tri, iso)
  - MetadataExtractor (GPS, device, serial reuse, stega)
  - run_all()         (agrégateur)
  - _http.py          (async_get, async_head, sync_get — mocks)
  - 10 connecteurs    (response parsing, erreurs, is_available)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.connectors.base import Finding
from agent.osint.target import Target, TargetType


# ── Helpers ──────────────────────────────────────────────────────────────────

def _finding(type_="account", source="test", **extracted) -> Finding:
    return Finding(type=type_, source=source, extracted=extracted)


def _target(raw: str, ttype: TargetType = TargetType.DOMAIN) -> Target:
    return Target(raw=raw, type=ttype, normalized=raw)


# ─────────────────────────────────────────────────────────────────────────────
# ANALYZERS
# ─────────────────────────────────────────────────────────────────────────────

def test_behavior_empty():
    from agent.osint.analyzers.behavior import BehaviorAnalyzer
    p = BehaviorAnalyzer().analyze([])
    assert p.language is None
    assert p.posts_per_day == 0.0
    assert p.sample_count == 0


def test_behavior_language_fr():
    from agent.osint.analyzers.behavior import BehaviorAnalyzer
    findings = [
        _finding(text="bonjour je suis ici avec vous et les amis"),
        _finding(text="merci pour ça, c'est très bien pour nous"),
    ]
    p = BehaviorAnalyzer().analyze(findings)
    assert p.language == "fr"
    assert "fr" in p.language_scores


def test_behavior_language_en():
    from agent.osint.analyzers.behavior import BehaviorAnalyzer
    findings = [
        _finding(text="hello this is what you need with the team"),
        _finding(text="thanks for that, your work is great and they are happy"),
    ]
    p = BehaviorAnalyzer().analyze(findings)
    assert p.language == "en"


def test_behavior_timestamps():
    from agent.osint.analyzers.behavior import BehaviorAnalyzer
    findings = [
        _finding(date="2024-01-01T10:00:00"),
        _finding(date="2024-01-03T10:00:00"),
        _finding(date="2024-01-05T10:00:00"),
    ]
    p = BehaviorAnalyzer().analyze(findings)
    assert p.posts_per_day > 0
    assert p.most_active_hour == 10
    assert p.timezone is not None


def test_behavior_topics():
    from agent.osint.analyzers.behavior import BehaviorAnalyzer
    text = "python python python django flask security hacking hacking"
    findings = [_finding(text=text)]
    p = BehaviorAnalyzer().analyze(findings)
    assert "python" in p.topics
    assert len(p.topics) <= 10


def test_behavior_weekday_ratio():
    from agent.osint.analyzers.behavior import BehaviorAnalyzer
    # 2024-01-01 = lundi (weekday)
    findings = [
        _finding(date="2024-01-01T12:00:00"),  # lundi
        _finding(date="2024-01-02T12:00:00"),  # mardi
        _finding(date="2024-01-06T12:00:00"),  # samedi
    ]
    p = BehaviorAnalyzer().analyze(findings)
    assert 0.0 <= p.weekday_ratio <= 1.0


def test_behavior_to_dict():
    from agent.osint.analyzers.behavior import BehaviorAnalyzer
    p = BehaviorAnalyzer().analyze([_finding(text="hello world")])
    d = p.to_dict()
    assert "language" in d
    assert "topics" in d
    assert isinstance(d["topics"], list)


# ── NetworkMapper ─────────────────────────────────────────────────────────────

def test_network_empty():
    from agent.osint.analyzers.network import NetworkMapper
    g = NetworkMapper().analyze([])
    assert g.nodes == []
    assert g.edges == []


def test_network_nodes_from_findings():
    from agent.osint.analyzers.network import NetworkMapper
    findings = [
        _finding(source="github", email="alice@example.com"),
        _finding(source="twitter", email="alice@example.com"),
    ]
    g = NetworkMapper().analyze(findings)
    node_ids = {n["id"] for n in g.nodes}
    assert any("github" in nid for nid in node_ids)
    assert any("twitter" in nid for nid in node_ids)


def test_network_triangulation():
    from agent.osint.analyzers.network import NetworkMapper
    findings = [
        _finding(source="src1", email="bob@x.com"),
        _finding(source="src2", email="bob@x.com"),
    ]
    g = NetworkMapper().analyze(findings)
    entities = [t["entity"] for t in g.triangulations]
    assert "bob@x.com" in entities


def test_network_no_triangulation_single_source():
    from agent.osint.analyzers.network import NetworkMapper
    findings = [
        _finding(source="src1", email="solo@x.com"),
        _finding(source="src1", email="solo@x.com"),
    ]
    g = NetworkMapper().analyze(findings)
    entities = [t["entity"] for t in g.triangulations]
    assert "solo@x.com" not in entities


def test_network_geo_cluster():
    from agent.osint.analyzers.network import NetworkMapper
    findings = [
        _finding(latitude=48.85, longitude=2.35),
        _finding(latitude=48.86, longitude=2.35),
        _finding(latitude=40.71, longitude=-74.0),
    ]
    g = NetworkMapper().analyze(findings)
    assert len(g.geo_clusters) >= 2


def test_network_to_dict():
    from agent.osint.analyzers.network import NetworkMapper
    g = NetworkMapper().analyze([_finding(source="x", email="a@b.com")])
    d = g.to_dict()
    assert "nodes" in d and "edges" in d and "triangulations" in d


# ── HistoricalScraper ─────────────────────────────────────────────────────────

def test_historical_empty():
    from agent.osint.analyzers.historical import HistoricalScraper
    tl = HistoricalScraper().analyze([])
    assert tl.events == []
    assert tl.earliest is None


def test_historical_sorted():
    from agent.osint.analyzers.historical import HistoricalScraper
    findings = [
        _finding(source="web", date="2023-06-15T10:00:00"),
        _finding(source="web", date="2022-01-01T00:00:00"),
        _finding(source="web", date="2024-12-31T23:59:59"),
    ]
    tl = HistoricalScraper().analyze(findings)
    assert tl.earliest < tl.latest
    ts = [e.timestamp for e in tl.events]
    assert ts == sorted(ts)


def test_historical_wayback_count():
    from agent.osint.analyzers.historical import HistoricalScraper
    findings = [
        _finding(source="wayback_machine", date="2020-05-01T00:00:00"),
        _finding(source="github", date="2021-01-01T00:00:00"),
    ]
    tl = HistoricalScraper().analyze(findings)
    assert tl.wayback_count == 1


def test_historical_iso_format():
    from agent.osint.analyzers.historical import HistoricalScraper
    findings = [_finding(source="x", date="2024-03-15T08:30:00")]
    tl = HistoricalScraper().analyze(findings)
    assert tl.events[0].iso.startswith("2024-03-15")


def test_historical_unix_timestamp():
    from agent.osint.analyzers.historical import HistoricalScraper
    findings = [_finding(source="x", timestamp=1700000000.0)]
    tl = HistoricalScraper().analyze(findings)
    assert len(tl.events) == 1
    assert tl.events[0].timestamp == 1700000000.0


def test_historical_to_dict():
    from agent.osint.analyzers.historical import HistoricalScraper
    findings = [_finding(source="x", date="2024-01-01T00:00:00")]
    d = HistoricalScraper().analyze(findings).to_dict()
    assert "events" in d and "earliest" in d and "total_events" in d


# ── MetadataExtractor ─────────────────────────────────────────────────────────

def test_metadata_empty():
    from agent.osint.analyzers.metadata import MetadataExtractor
    r = MetadataExtractor().analyze([])
    assert r.gps_points == []
    assert r.serial_reuse == []


def test_metadata_gps():
    from agent.osint.analyzers.metadata import MetadataExtractor
    findings = [
        _finding(source="img1", latitude=48.8566, longitude=2.3522),
        _finding(source="img2", GPSLatitude=51.5074, GPSLongitude=-0.1278),
    ]
    r = MetadataExtractor().analyze(findings)
    assert len(r.gps_points) == 2
    assert r.gps_points[0]["lat"] == 48.8566


def test_metadata_device():
    from agent.osint.analyzers.metadata import MetadataExtractor
    findings = [
        _finding(Make="Apple", Model="iPhone 14"),
        _finding(Make="Apple", Model="iPhone 14"),
    ]
    r = MetadataExtractor().analyze(findings)
    assert "Make=Apple" in r.devices_seen
    assert r.devices_seen["Make=Apple"] == 2


def test_metadata_serial_reuse():
    from agent.osint.analyzers.metadata import MetadataExtractor
    findings = [
        _finding(source="photo1.jpg", SerialNumber="SN12345", image="photo1.jpg"),
        _finding(source="photo2.jpg", SerialNumber="SN12345", image="photo2.jpg"),
    ]
    r = MetadataExtractor().analyze(findings)
    assert len(r.serial_reuse) == 1
    assert r.serial_reuse[0]["serial"] == "SN12345"


def test_metadata_stega():
    from agent.osint.analyzers.metadata import MetadataExtractor
    findings = [
        Finding(type="stega_lsb", source="img.png",
                extracted={"raw": "hidden data here", "image": "img.png"}),
    ]
    r = MetadataExtractor().analyze(findings)
    assert len(r.stega_signals) == 1
    assert r.stega_signals[0]["type"] == "stega_lsb"


def test_metadata_to_dict():
    from agent.osint.analyzers.metadata import MetadataExtractor
    r = MetadataExtractor().analyze([_finding(Make="Sony")])
    d = r.to_dict()
    assert "gps_points" in d and "devices" in d and "serial_reuse" in d


# ── run_all ───────────────────────────────────────────────────────────────────

def test_run_all_keys():
    from agent.osint.analyzers import run_all
    findings = [_finding(text="hello world", date="2024-01-01T12:00:00")]
    result = run_all(findings)
    assert set(result.keys()) == {"behavior", "network", "historical", "metadata"}


def test_run_all_returns_objects_with_to_dict():
    from agent.osint.analyzers import run_all
    result = run_all([_finding(source="x", email="a@b.com",
                                date="2024-06-01T10:00:00")])
    for v in result.values():
        assert hasattr(v, "to_dict")
        d = v.to_dict()
        assert isinstance(d, dict)


# ─────────────────────────────────────────────────────────────────────────────
# BASE HTTP
# ─────────────────────────────────────────────────────────────────────────────

def test_http_sync_get_no_libs():
    """Sans requests ni httpx, retourne ok=False proprement."""
    from agent.osint.connectors.python import _http
    orig = _http._REQUESTS
    _http._REQUESTS = False
    result = _http._sync_get("http://example.com")
    _http._REQUESTS = orig
    assert result["ok"] is False
    assert "no http library" in result["data"]


def test_http_async_get_mocked():
    from agent.osint.connectors.python._http import async_get

    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"key": "val"}
    mock_resp.text = '{"key": "val"}'

    async def run():
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client
            return await async_get("http://test.local/api")

    result = asyncio.run(run())
    assert result["ok"] is True
    assert result["status"] == 200


def test_http_async_get_retry_on_429():
    from agent.osint.connectors.python._http import async_get

    call_count = 0

    async def mock_get(*a, **kw):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.is_success = call_count > 1
        resp.status_code = 429 if call_count == 1 else 200
        resp.headers = {"content-type": "text/plain"}
        resp.text = "ok"
        resp.json.return_value = {}
        return resp

    async def run():
        with patch("httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = mock_get
            mock_cls.return_value = mock_client
            return await async_get("http://test.local/", retries=2)

    result = asyncio.run(run())
    assert call_count >= 2


# ─────────────────────────────────────────────────────────────────────────────
# CONNECTEURS PYTHON
# ─────────────────────────────────────────────────────────────────────────────

def _mock_async_get(resp_data, status=200, ok=True):
    """Patch agent.osint.connectors.python._http.async_get."""
    async def _fake(*a, **kw):
        return {"ok": ok, "status": status, "data": resp_data, "elapsed_ms": 10}
    return _fake


def _mock_async_head(status=200, ok=True):
    async def _fake(*a, **kw):
        return {"ok": ok, "status": status, "elapsed_ms": 5}
    return _fake


# crtsh ───────────────────────────────────────────────────────────────────────

def test_crtsh_parses_subdomains():
    from agent.osint.connectors.python.crtsh import CrtShConnector
    data = [
        {"name_value": "sub.example.com\n*.example.com", "issuer_ca_id": 1,
         "not_before": "2024-01-01T00:00:00"},
    ]
    t = _target("example.com")
    with patch("agent.osint.connectors.python.crtsh.async_get",
               _mock_async_get(data)):
        result = asyncio.run(CrtShConnector().query(t))
    assert result.success
    subdomains = [f.extracted["subdomain"] for f in result.findings]
    assert "sub.example.com" in subdomains
    assert not any(s.startswith("*") for s in subdomains)


def test_crtsh_empty_response():
    from agent.osint.connectors.python.crtsh import CrtShConnector
    t = _target("ghost.org")
    with patch("agent.osint.connectors.python.crtsh.async_get",
               _mock_async_get([])):
        result = asyncio.run(CrtShConnector().query(t))
    assert result.success
    assert result.findings == []


def test_crtsh_error():
    from agent.osint.connectors.python.crtsh import CrtShConnector
    t = _target("x.com")
    with patch("agent.osint.connectors.python.crtsh.async_get",
               _mock_async_get("error", status=500, ok=False)):
        result = asyncio.run(CrtShConnector().query(t))
    assert not result.success


# hibp ────────────────────────────────────────────────────────────────────────

def test_hibp_breach_found():
    from agent.osint.connectors.python.hibp import HibpConnector
    data = [{"Name": "Adobe", "Domain": "adobe.com", "BreachDate": "2013-10-04",
             "DataClasses": ["Email", "Password"], "PwnCount": 153000000,
             "IsVerified": True, "IsSensitive": False}]
    t = _target("user@test.com", TargetType.EMAIL)
    with patch("agent.osint.connectors.python.hibp.async_get",
               _mock_async_get(data, status=200)):
        result = asyncio.run(HibpConnector().query(t))
    assert result.success
    assert len(result.findings) == 1
    assert result.findings[0].extracted["breach_name"] == "Adobe"


def test_hibp_no_breach():
    from agent.osint.connectors.python.hibp import HibpConnector
    t = _target("clean@test.com", TargetType.EMAIL)
    with patch("agent.osint.connectors.python.hibp.async_get",
               _mock_async_get("", status=404, ok=False)):
        result = asyncio.run(HibpConnector().query(t))
    assert result.success
    assert result.findings == []


def test_hibp_no_key_401():
    from agent.osint.connectors.python.hibp import HibpConnector
    t = _target("x@y.com", TargetType.EMAIL)
    with patch("agent.osint.connectors.python.hibp.async_get",
               _mock_async_get("Unauthorized", status=401, ok=False)):
        result = asyncio.run(HibpConnector().query(t))
    assert not result.success
    assert "clé" in (result.error or "").lower() or "HIBP" in (result.error or "")


# ipapi ───────────────────────────────────────────────────────────────────────

def test_ipapi_success():
    from agent.osint.connectors.python.ipapi import IpApiConnector
    data = {
        "status": "success", "country": "France", "countryCode": "FR",
        "city": "Paris", "lat": 48.85, "lon": 2.35,
        "isp": "OVH", "org": "OVH SAS", "as": "AS16276", "asname": "OVH",
    }
    t = _target("1.2.3.4", TargetType.IP)
    with patch("agent.osint.connectors.python.ipapi.async_get",
               _mock_async_get(data)):
        result = asyncio.run(IpApiConnector().query(t))
    assert result.success
    assert result.findings[0].extracted["city"] == "Paris"
    assert result.findings[0].extracted["latitude"] == 48.85


def test_ipapi_fail_status():
    from agent.osint.connectors.python.ipapi import IpApiConnector
    data = {"status": "fail", "message": "private range"}
    t = _target("192.168.0.1", TargetType.IP)
    with patch("agent.osint.connectors.python.ipapi.async_get",
               _mock_async_get(data)):
        result = asyncio.run(IpApiConnector().query(t))
    assert not result.success


# whois_py ────────────────────────────────────────────────────────────────────

def test_whois_py_unavailable():
    from agent.osint.connectors.python import whois_py
    orig = whois_py._HAS_WHOIS
    whois_py._HAS_WHOIS = False
    t = _target("example.com")
    result = asyncio.run(whois_py.WhoisPyConnector().query(t))
    whois_py._HAS_WHOIS = orig
    assert not result.success
    assert "python-whois" in (result.error or "")


def test_whois_py_success():
    from agent.osint.connectors.python import whois_py

    class FakeW:
        domain_name = "example.com"
        registrar = "ICANN"
        creation_date = "2000-01-01"
        expiration_date = "2030-01-01"
        updated_date = "2023-01-01"
        name_servers = ["ns1.example.com"]
        status = "active"
        emails = "admin@example.com"
        dnssec = "unsigned"

    with patch.object(whois_py, "_HAS_WHOIS", True), \
         patch("agent.osint.connectors.python.whois_py._do_whois",
               return_value={"domain": "example.com", "registrar": "ICANN",
                             "creation_date": "2000-01-01", "expiration_date": "",
                             "updated_date": "", "name_servers": "",
                             "status": "active", "emails": "", "dnssec": "",
                             "org": "", "country": "", "city": "", "address": ""}):
        t = _target("example.com")
        result = asyncio.run(whois_py.WhoisPyConnector().query(t))
    assert result.success
    assert result.findings[0].type == "whois"


# dns_py ──────────────────────────────────────────────────────────────────────

def test_dns_py_unavailable():
    from agent.osint.connectors.python import dns_py
    orig = dns_py._HAS_DNS
    dns_py._HAS_DNS = False
    t = _target("example.com")
    result = asyncio.run(dns_py.DnsPyConnector().query(t))
    dns_py._HAS_DNS = orig
    assert not result.success


def test_dns_py_resolves():
    from agent.osint.connectors.python import dns_py
    mock_records = [
        {"type": "A", "value": "93.184.216.34"},
        {"type": "MX", "value": "mail.example.com", "priority": 10},
    ]
    with patch.object(dns_py, "_HAS_DNS", True), \
         patch("agent.osint.connectors.python.dns_py._resolve_all",
               return_value=mock_records):
        t = _target("example.com")
        result = asyncio.run(dns_py.DnsPyConnector().query(t))
    assert result.success
    types = [f.extracted["record_type"] for f in result.findings]
    assert "A" in types and "MX" in types


# gravatar_py ─────────────────────────────────────────────────────────────────

def test_gravatar_found():
    from agent.osint.connectors.python.gravatar_py import GravatarPyConnector
    t = _target("user@example.com", TargetType.EMAIL)
    with patch("agent.osint.connectors.python.gravatar_py.async_head",
               _mock_async_head(status=200, ok=True)):
        result = asyncio.run(GravatarPyConnector().query(t))
    assert result.success
    assert len(result.findings) == 1
    assert result.findings[0].type == "account"
    assert result.findings[0].source == "gravatar"


def test_gravatar_not_found():
    from agent.osint.connectors.python.gravatar_py import GravatarPyConnector
    t = _target("nobody@nowhere.com", TargetType.EMAIL)
    with patch("agent.osint.connectors.python.gravatar_py.async_head",
               _mock_async_head(status=404, ok=False)):
        result = asyncio.run(GravatarPyConnector().query(t))
    assert result.success
    assert result.findings == []


# wayback_cdx ─────────────────────────────────────────────────────────────────

def test_wayback_cdx_parses():
    from agent.osint.connectors.python.wayback_cdx import WaybackCdxConnector
    data = [
        ["timestamp", "original", "statuscode", "mimetype"],
        ["20231210153042", "https://example.com/page", "200", "text/html"],
        ["20220501120000", "https://sub.example.com/", "301", "text/html"],
    ]
    t = _target("example.com")
    with patch("agent.osint.connectors.python.wayback_cdx.async_get",
               _mock_async_get(data)):
        result = asyncio.run(WaybackCdxConnector().query(t))
    assert result.success
    assert len(result.findings) == 2
    assert result.findings[0].type == "wayback_snapshot"
    assert "wayback_url" in result.findings[0].extracted


def test_wayback_cdx_empty():
    from agent.osint.connectors.python.wayback_cdx import WaybackCdxConnector
    t = _target("new-domain.io")
    with patch("agent.osint.connectors.python.wayback_cdx.async_get",
               _mock_async_get([])):
        result = asyncio.run(WaybackCdxConnector().query(t))
    assert result.success
    assert result.findings == []


# intelx_py ───────────────────────────────────────────────────────────────────

def test_intelx_no_key():
    from agent.osint.connectors.python.intelx_py import IntelXConnector
    c = IntelXConnector()
    assert not c.is_available()
    t = _target("x@y.com", TargetType.EMAIL)
    result = asyncio.run(c.query(t))
    assert not result.success
    assert "INTELX_API_KEY" in (result.error or "")


def test_intelx_with_key():
    from agent.osint.connectors.python import intelx_py
    data = {"selectors": [
        {"selectorvalue": "x@y.com", "selectortype": 1, "bucket": "pastes", "date": "2024-01-01"},
    ]}
    t = _target("x@y.com", TargetType.EMAIL)
    with patch.dict("os.environ", {"INTELX_API_KEY": "testkey"}), \
         patch("agent.osint.connectors.python.intelx_py.async_get",
               _mock_async_get(data)):
        result = asyncio.run(intelx_py.IntelXConnector().query(t))
    assert result.success
    assert len(result.findings) == 1
    assert result.findings[0].type == "leak_reference"


# shodan_py ───────────────────────────────────────────────────────────────────

def test_shodan_no_key():
    from agent.osint.connectors.python.shodan_py import ShodanPyConnector
    c = ShodanPyConnector()
    assert not c.is_available()
    t = _target("1.2.3.4", TargetType.IP)
    result = asyncio.run(c.query(t))
    assert not result.success


def test_shodan_parses_host():
    from agent.osint.connectors.python import shodan_py
    data = {
        "ip_str": "1.2.3.4", "hostnames": ["host.example.com"], "domains": ["example.com"],
        "org": "Acme Corp", "isp": "ISP", "asn": "AS1234", "country_name": "US",
        "city": "New York", "latitude": 40.71, "longitude": -74.0,
        "os": None, "ports": [80, 443], "tags": [], "vulns": {},
        "last_update": "2024-01-01", "data": [],
    }
    t = _target("1.2.3.4", TargetType.IP)
    with patch.dict("os.environ", {"SHODAN_API_KEY": "testkey"}), \
         patch("agent.osint.connectors.python.shodan_py.async_get",
               _mock_async_get(data)):
        result = asyncio.run(shodan_py.ShodanPyConnector().query(t))
    assert result.success
    host_f = next(f for f in result.findings if f.type == "host_info")
    assert host_f.extracted["org"] == "Acme Corp"
    assert 80 in host_f.extracted["ports"]


def test_shodan_404():
    from agent.osint.connectors.python import shodan_py
    t = _target("10.0.0.1", TargetType.IP)
    with patch.dict("os.environ", {"SHODAN_API_KEY": "testkey"}), \
         patch("agent.osint.connectors.python.shodan_py.async_get",
               _mock_async_get("Not Found", status=404, ok=False)):
        result = asyncio.run(shodan_py.ShodanPyConnector().query(t))
    assert result.success
    assert result.findings == []


# hackertarget_py ─────────────────────────────────────────────────────────────

def test_hackertarget_hostsearch():
    from agent.osint.connectors.python.hackertarget_py import HackerTargetConnector
    hostsearch_resp = "sub1.example.com,1.2.3.4\nsub2.example.com,5.6.7.8"

    async def mock_get(url, **kw):
        if "hostsearch" in url:
            return {"ok": True, "status": 200, "data": hostsearch_resp, "elapsed_ms": 5}
        return {"ok": True, "status": 200, "data": "raw data", "elapsed_ms": 5}

    t = _target("example.com")
    with patch("agent.osint.connectors.python.hackertarget_py.async_get", mock_get):
        result = asyncio.run(HackerTargetConnector().query(t))
    assert result.success
    subs = [f.extracted["subdomain"] for f in result.findings
            if f.type == "dns_record"]
    assert "sub1.example.com" in subs


# emailrep_py ─────────────────────────────────────────────────────────────────

def test_emailrep_reputation():
    from agent.osint.connectors.python.emailrep_py import EmailRepConnector
    data = {
        "email": "test@example.com",
        "reputation": "high",
        "suspicious": False,
        "references": 12,
        "details": {
            "blacklisted": False, "malicious_activity": False,
            "spam": False, "deliverable": True, "free_provider": False,
            "disposable": False, "first_seen": "2019-01-01", "last_seen": "2024-01-01",
            "seen_count": 12, "profiles": ["github"],
        }
    }
    t = _target("test@example.com", TargetType.EMAIL)
    with patch("agent.osint.connectors.python.emailrep_py.async_get",
               _mock_async_get(data)):
        result = asyncio.run(EmailRepConnector().query(t))
    assert result.success
    f = result.findings[0]
    assert f.type == "email_reputation"
    assert f.extracted["reputation"] == "high"
    assert f.extracted["deliverable"] is True


def test_emailrep_rate_limited():
    from agent.osint.connectors.python.emailrep_py import EmailRepConnector
    t = _target("a@b.com", TargetType.EMAIL)
    with patch("agent.osint.connectors.python.emailrep_py.async_get",
               _mock_async_get("rate limit", status=429, ok=False)):
        result = asyncio.run(EmailRepConnector().query(t))
    assert not result.success
    assert "rate" in (result.error or "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# INTÉGRATION — engine.analyzers injecté
# ─────────────────────────────────────────────────────────────────────────────

def test_engine_report_has_analyzers_key():
    """OSINTReport.analyzers est un dict (même vide)."""
    from agent.osint.engine import OSINTReport
    from agent.osint.target import TargetNormalizer
    import time
    t = TargetNormalizer.detect("example.com")
    r = OSINTReport(target=t, mode="self_audit",
                    started_at=time.time(), completed_at=time.time())
    assert isinstance(r.analyzers, dict)


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [OK] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
    total = passed + failed
    print(f"\n[RESULTS] Session 4 OSINT -- {passed}/{total} passed"
          + (f", {failed} failed" if failed else " OK"))
