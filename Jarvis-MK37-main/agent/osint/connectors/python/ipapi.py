"""
ip-api.com — géolocalisation + ASN + organisation pour une IP.
Cible : IP | sans clé API (free tier, 45 req/min).
"""
from __future__ import annotations

import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_FIELDS = (
    "status,message,continent,country,countryCode,region,regionName,"
    "city,district,zip,lat,lon,timezone,offset,currency,isp,org,as,"
    "asname,reverse,mobile,proxy,hosting,query"
)


class IpApiConnector(Connector):
    name         = "ipapi"
    supports     = {TargetType.IP}
    requires_key = False
    rate_limit   = 45
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        ip = target.normalized
        url = f"http://ip-api.com/json/{ip}"
        resp = await async_get(url, params={"fields": _FIELDS}, timeout=8.0)
        elapsed = int((time.monotonic() - t0) * 1000)

        if not resp["ok"]:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"ipapi {resp['status']}: {str(resp['data'])[:120]}",
                elapsed_ms=elapsed,
            )

        data = resp["data"]
        if not isinstance(data, dict) or data.get("status") == "fail":
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"ipapi fail: {data.get('message', 'unknown')}",
                elapsed_ms=elapsed,
            )

        finding = Finding(
            type="geoip",
            source="ip-api.com",
            extracted={
                "ip":          ip,
                "country":     data.get("country"),
                "countryCode": data.get("countryCode"),
                "region":      data.get("regionName"),
                "city":        data.get("city"),
                "zip":         data.get("zip"),
                "latitude":    data.get("lat"),
                "longitude":   data.get("lon"),
                "timezone":    data.get("timezone"),
                "isp":         data.get("isp"),
                "org":         data.get("org"),
                "asn":         data.get("as"),
                "asname":      data.get("asname"),
                "reverse_dns": data.get("reverse"),
                "is_mobile":   data.get("mobile"),
                "is_proxy":    data.get("proxy"),
                "is_hosting":  data.get("hosting"),
            },
            confidence=0.85,
        )
        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=[finding], elapsed_ms=elapsed,
        )


get_registry().register(IpApiConnector())
