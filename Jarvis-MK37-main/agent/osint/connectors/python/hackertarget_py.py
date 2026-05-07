"""
HackerTarget — endpoints gratuits : reverse IP, hostsearch, ASN lookup, WHOIS.
Cible : DOMAIN, IP | sans clé API (free tier : 100 req/jour).
"""
from __future__ import annotations

import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_BASE = "https://api.hackertarget.com"


class HackerTargetConnector(Connector):
    name         = "hackertarget_py"
    supports     = {TargetType.DOMAIN, TargetType.IP}
    requires_key = False
    rate_limit   = 100
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        val = target.normalized
        is_ip = target.type == TargetType.IP

        findings: list[Finding] = []
        errors: list[str] = []

        tasks = []
        if is_ip:
            tasks = [
                ("reverse_ip", f"{_BASE}/reverseiplookup/", {"q": val}),
                ("geoip", f"{_BASE}/geoip/", {"q": val}),
            ]
        else:
            tasks = [
                ("hostsearch", f"{_BASE}/hostsearch/", {"q": val}),
                ("whois",      f"{_BASE}/whois/",      {"q": val}),
                ("dnslookup",  f"{_BASE}/dnslookup/",  {"q": val}),
            ]

        import asyncio
        async def _fetch(ftype: str, url: str, params: dict):
            r = await async_get(url, params=params, timeout=10.0)
            return ftype, r

        results = await asyncio.gather(*[_fetch(t, u, p) for t, u, p in tasks])
        elapsed = int((time.monotonic() - t0) * 1000)

        for ftype, resp in results:
            if not resp["ok"]:
                errors.append(f"{ftype}: {resp['status']}")
                continue
            text = resp["data"] if isinstance(resp["data"], str) else str(resp["data"])
            if not text.strip() or text.startswith("error check"):
                continue

            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if ftype == "hostsearch":
                for line in lines:
                    parts = line.split(",")
                    host = parts[0] if parts else line
                    ip   = parts[1] if len(parts) > 1 else ""
                    findings.append(Finding(
                        type="dns_record",
                        source="hackertarget",
                        extracted={
                            "domain": val, "subdomain": host,
                            "ip": ip, "record_type": "A",
                        },
                        confidence=0.75,
                    ))
            elif ftype == "reverse_ip":
                for line in lines:
                    findings.append(Finding(
                        type="reverse_dns",
                        source="hackertarget",
                        extracted={"ip": val, "domain": line},
                        confidence=0.75,
                    ))
            elif ftype in ("whois", "dnslookup", "geoip"):
                findings.append(Finding(
                    type=ftype,
                    source="hackertarget",
                    extracted={
                        "target": val,
                        "raw": text[:1000],
                    },
                    confidence=0.7,
                ))

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
            error="; ".join(errors) if errors else None,
        )


get_registry().register(HackerTargetConnector())
