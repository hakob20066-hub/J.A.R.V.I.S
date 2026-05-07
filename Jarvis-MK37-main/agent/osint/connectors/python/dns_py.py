"""
dnspython — résolution DNS complète (A, AAAA, MX, NS, TXT, CNAME, SOA).
Cible : DOMAIN, IP (PTR) | sans clé API.
"""
from __future__ import annotations

import asyncio
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.target import Target, TargetType

try:
    import dns.resolver
    import dns.reversename
    _HAS_DNS = True
except ImportError:
    _HAS_DNS = False

_RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA")


def _resolve_all(domain: str, is_ip: bool) -> list[dict]:
    results = []
    if is_ip:
        try:
            rev = dns.reversename.from_address(domain)
            answers = dns.resolver.resolve(rev, "PTR")
            for a in answers:
                results.append({"type": "PTR", "value": str(a)})
        except Exception:
            pass
        return results

    for rtype in _RECORD_TYPES:
        try:
            answers = dns.resolver.resolve(domain, rtype)
            for a in answers:
                val = str(a)
                rec: dict = {"type": rtype, "value": val}
                if rtype == "MX":
                    rec["priority"] = getattr(a, "preference", None)
                results.append(rec)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                dns.resolver.NoNameservers):
            pass
        except Exception:
            pass
    return results


class DnsPyConnector(Connector):
    name         = "dns_py"
    supports     = {TargetType.DOMAIN, TargetType.IP}
    requires_key = False
    rate_limit   = 120
    backend      = "python"

    def is_available(self) -> bool:
        return _HAS_DNS

    async def query(self, target: Target) -> ConnectorResult:
        if not _HAS_DNS:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="dnspython not installed (pip install dnspython)",
            )
        t0 = time.monotonic()
        is_ip = target.type == TargetType.IP
        try:
            records = await asyncio.to_thread(_resolve_all, target.normalized, is_ip)
        except Exception as e:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=str(e), elapsed_ms=int((time.monotonic()-t0)*1000),
            )
        elapsed = int((time.monotonic() - t0) * 1000)

        findings: list[Finding] = []
        for rec in records:
            findings.append(Finding(
                type="dns_record",
                source="dns_py",
                extracted={
                    "domain": target.normalized,
                    "record_type": rec["type"],
                    "value": rec["value"],
                    "priority": rec.get("priority"),
                },
                confidence=0.99,
            ))

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
        )


get_registry().register(DnsPyConnector())
