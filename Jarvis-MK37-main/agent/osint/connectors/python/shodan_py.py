"""
Shodan — ports, services, CVE pour une IP.
Cible : IP | clé SHODAN_API_KEY requise.
"""
from __future__ import annotations

import asyncio
import os
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "SHODAN_API_KEY"
_BASE    = "https://api.shodan.io"


def _port_summary(services: list[dict]) -> list[dict]:
    out = []
    for s in services[:30]:
        if not isinstance(s, dict):
            continue
        out.append({
            "port":      s.get("port"),
            "transport": s.get("transport", "tcp"),
            "product":   s.get("product", ""),
            "version":   s.get("version", ""),
            "cpe":       s.get("cpe", []),
            "banner":    str(s.get("data", ""))[:200],
            "timestamp": s.get("timestamp", ""),
        })
    return out


class ShodanPyConnector(Connector):
    name         = "shodan_py"
    supports     = {TargetType.IP}
    requires_key = True
    rate_limit   = 60
    backend      = "python"

    def _key(self) -> str:
        return os.environ.get(_KEY_ENV, "")

    def is_available(self) -> bool:
        return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="SHODAN_API_KEY not set", elapsed_ms=0,
            )

        ip = target.normalized
        url = f"{_BASE}/shodan/host/{ip}"
        resp = await async_get(url, params={"key": key}, timeout=15.0)
        elapsed = int((time.monotonic() - t0) * 1000)

        if resp["status"] == 404:
            return ConnectorResult(
                connector=self.name, target=target, success=True,
                findings=[], elapsed_ms=elapsed,
            )
        if not resp["ok"]:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"shodan {resp['status']}: {str(resp['data'])[:120]}",
                elapsed_ms=elapsed,
            )

        d = resp["data"]
        if not isinstance(d, dict):
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="shodan: unexpected response", elapsed_ms=elapsed,
            )

        findings: list[Finding] = []

        # Finding principal : infos globales
        findings.append(Finding(
            type="host_info",
            source="shodan",
            extracted={
                "ip":           ip,
                "hostnames":    d.get("hostnames", []),
                "domains":      d.get("domains", []),
                "org":          d.get("org", ""),
                "isp":          d.get("isp", ""),
                "asn":          d.get("asn", ""),
                "country":      d.get("country_name", ""),
                "city":         d.get("city", ""),
                "latitude":     d.get("latitude"),
                "longitude":    d.get("longitude"),
                "os":           d.get("os", ""),
                "ports":        d.get("ports", []),
                "tags":         d.get("tags", []),
                "vulns":        list(d.get("vulns", {}).keys()),
                "last_update":  d.get("last_update", ""),
            },
            confidence=0.9,
        ))

        # Finding par service
        services = d.get("data", [])
        for svc in _port_summary(services):
            findings.append(Finding(
                type="open_port",
                source="shodan",
                extracted={"ip": ip, **svc},
                confidence=0.9,
            ))

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
        )


get_registry().register(ShodanPyConnector())
