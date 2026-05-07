"""
AbuseIPDB — rapports d'abus pour une IP.
Cibles : IP | clé ABUSEIPDB_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "ABUSEIPDB_KEY"
_BASE    = "https://api.abuseipdb.com/api/v2"


class AbuseIPDBConnector(Connector):
    name         = "abuseipdb_py"
    supports     = {TargetType.IP}
    requires_key = True
    rate_limit   = 60
    backend      = "python"

    def _key(self): return os.environ.get(_KEY_ENV, "")
    def is_available(self): return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="ABUSEIPDB_KEY not set", elapsed_ms=0)
        resp = await async_get(f"{_BASE}/check",
                               params={"ipAddress": target.normalized, "maxAgeInDays": 90,
                                       "verbose": True},
                               headers={"Key": key, "Accept": "application/json"},
                               timeout=10.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"abuseipdb {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        data = d.get("data", d) if isinstance(d, dict) else {}
        finding = Finding(
            type="abuse_report",
            source="abuseipdb",
            url=f"https://www.abuseipdb.com/check/{target.normalized}",
            extracted={
                "ip":                  target.normalized,
                "abuse_score":         data.get("abuseConfidenceScore", 0),
                "total_reports":       data.get("totalReports", 0),
                "num_distinct_users":  data.get("numDistinctUsers", 0),
                "last_reported":       data.get("lastReportedAt", ""),
                "country":             data.get("countryCode", ""),
                "isp":                 data.get("isp", ""),
                "domain":              data.get("domain", ""),
                "is_tor":              data.get("isTor", False),
                "is_public":           data.get("isPublic", True),
                "usage_type":          data.get("usageType", ""),
            },
            confidence=0.88,
        )
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=[finding], elapsed_ms=elapsed)


get_registry().register(AbuseIPDBConnector())
