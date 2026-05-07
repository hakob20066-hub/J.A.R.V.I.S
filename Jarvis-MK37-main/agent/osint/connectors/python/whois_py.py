"""
python-whois — WHOIS domaine/IP natif Python (fallback cross-platform).
Cible : DOMAIN, IP | sans clé API.
"""
from __future__ import annotations

import asyncio
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.target import Target, TargetType

try:
    import whois as _whois_lib
    _HAS_WHOIS = True
except ImportError:
    _HAS_WHOIS = False


def _safe_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v if x)
    return str(v)


def _do_whois(domain: str) -> dict:
    w = _whois_lib.whois(domain)
    return {
        "domain":       _safe_str(w.domain_name),
        "registrar":    _safe_str(w.registrar),
        "creation_date": _safe_str(w.creation_date),
        "expiration_date": _safe_str(w.expiration_date),
        "updated_date": _safe_str(w.updated_date),
        "name_servers": _safe_str(w.name_servers),
        "status":       _safe_str(w.status),
        "emails":       _safe_str(w.emails),
        "dnssec":       _safe_str(w.dnssec),
        "org":          _safe_str(getattr(w, "org", None)),
        "country":      _safe_str(getattr(w, "country", None)),
        "city":         _safe_str(getattr(w, "city", None)),
        "address":      _safe_str(getattr(w, "address", None)),
    }


class WhoisPyConnector(Connector):
    name         = "whois_py"
    supports     = {TargetType.DOMAIN, TargetType.IP}
    requires_key = False
    rate_limit   = 30
    backend      = "python"

    def is_available(self) -> bool:
        return _HAS_WHOIS

    async def query(self, target: Target) -> ConnectorResult:
        if not _HAS_WHOIS:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="python-whois not installed (pip install python-whois)",
            )
        t0 = time.monotonic()
        domain = target.normalized
        try:
            data = await asyncio.to_thread(_do_whois, domain)
        except Exception as e:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"whois error: {e}", elapsed_ms=int((time.monotonic()-t0)*1000),
            )
        elapsed = int((time.monotonic() - t0) * 1000)
        finding = Finding(
            type="whois",
            source="whois_py",
            extracted={"domain": domain, **data},
            confidence=0.9,
        )
        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=[finding], elapsed_ms=elapsed,
        )


get_registry().register(WhoisPyConnector())
