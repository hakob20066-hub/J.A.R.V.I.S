"""
Censys — host search (ports, certificats, services) pour une IP.
Cibles : IP | clés CENSYS_API_ID + CENSYS_API_SECRET requises.
"""
from __future__ import annotations
import base64, os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_ID_ENV     = "CENSYS_API_ID"
_SECRET_ENV = "CENSYS_API_SECRET"
_BASE       = "https://search.censys.io/api/v2"


class CensysConnector(Connector):
    name         = "censys_py"
    supports     = {TargetType.IP}
    requires_key = True
    rate_limit   = 120
    backend      = "python"

    def _creds(self) -> tuple[str, str]:
        return os.environ.get(_ID_ENV, ""), os.environ.get(_SECRET_ENV, "")

    def is_available(self) -> bool:
        i, s = self._creds()
        return bool(i and s)

    def _auth(self) -> dict:
        i, s = self._creds()
        cred = base64.b64encode(f"{i}:{s}".encode()).decode()
        return {"Authorization": f"Basic {cred}"}

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        if not self.is_available():
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="CENSYS_API_ID + CENSYS_API_SECRET required", elapsed_ms=0)
        resp = await async_get(f"{_BASE}/hosts/{target.normalized}",
                               headers=self._auth(), timeout=12.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if resp["status"] == 404:
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"censys {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        result = d.get("result", d) if isinstance(d, dict) else {}
        services = result.get("services", [])
        findings: list[Finding] = []
        findings.append(Finding(
            type="host_info",
            source="censys",
            url=f"https://search.censys.io/hosts/{target.normalized}",
            extracted={
                "ip":           target.normalized,
                "autonomous_system": result.get("autonomous_system", {}).get("name", ""),
                "asn":          result.get("autonomous_system", {}).get("asn", ""),
                "country":      result.get("location", {}).get("country", ""),
                "city":         result.get("location", {}).get("city", ""),
                "latitude":     result.get("location", {}).get("coordinates", {}).get("latitude"),
                "longitude":    result.get("location", {}).get("coordinates", {}).get("longitude"),
                "last_updated": result.get("last_updated_at", ""),
                "open_ports":   [s.get("port") for s in services if s.get("port")],
            },
            confidence=0.9,
        ))
        for svc in services[:10]:
            findings.append(Finding(
                type="open_port",
                source="censys",
                extracted={
                    "ip":            target.normalized,
                    "port":          svc.get("port"),
                    "transport":     svc.get("transport_protocol", ""),
                    "service_name":  svc.get("service_name", ""),
                    "extended_name": svc.get("extended_service_name", ""),
                    "certificate":   svc.get("certificate", ""),
                },
                confidence=0.9,
            ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed)


get_registry().register(CensysConnector())
