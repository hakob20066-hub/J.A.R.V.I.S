"""
Numverify — validation et enrichissement numéro de téléphone.
Cibles : PHONE | clé NUMVERIFY_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "NUMVERIFY_KEY"
_BASE    = "http://apilayer.net/api"   # HTTP only sur free tier


class NumverifyConnector(Connector):
    name         = "numverify_py"
    supports     = {TargetType.PHONE}
    requires_key = True
    rate_limit   = 100
    backend      = "python"

    def _key(self): return os.environ.get(_KEY_ENV, "")
    def is_available(self): return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="NUMVERIFY_KEY not set", elapsed_ms=0)
        phone = target.normalized.lstrip("+")
        resp = await async_get(f"{_BASE}/validate",
                               params={"access_key": key, "number": phone,
                                       "country_code": "", "format": 1},
                               timeout=10.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"numverify {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        if not isinstance(d, dict):
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="numverify: unexpected response", elapsed_ms=elapsed)
        if d.get("error"):
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=str(d["error"]), elapsed_ms=elapsed)
        finding = Finding(
            type="phone_info",
            source="numverify",
            extracted={
                "phone":           target.normalized,
                "valid":           d.get("valid", False),
                "number":          d.get("number", ""),
                "local_format":    d.get("local_format", ""),
                "international":   d.get("international_format", ""),
                "country_prefix":  d.get("country_prefix", ""),
                "country_code":    d.get("country_code", ""),
                "country_name":    d.get("country_name", ""),
                "location":        d.get("location", ""),
                "carrier":         d.get("carrier", ""),
                "line_type":       d.get("line_type", ""),
            },
            confidence=0.88,
        )
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=[finding], elapsed_ms=elapsed)


get_registry().register(NumverifyConnector())
