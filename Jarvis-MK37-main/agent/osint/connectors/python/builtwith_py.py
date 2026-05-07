"""
BuiltWith — stack technologique d'un domaine.
Cibles : DOMAIN | clé BW_API_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "BW_API_KEY"
_BASE    = "https://api.builtwith.com/v21/api.json"


class BuiltWithConnector(Connector):
    name         = "builtwith_py"
    supports     = {TargetType.DOMAIN}
    requires_key = True
    rate_limit   = 20
    backend      = "python"

    def _key(self): return os.environ.get(_KEY_ENV, "")
    def is_available(self): return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="BW_API_KEY not set", elapsed_ms=0)
        resp = await async_get(_BASE,
                               params={"KEY": key, "LOOKUP": target.normalized},
                               timeout=15.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"builtwith {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        if not isinstance(d, dict):
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="builtwith: unexpected response", elapsed_ms=elapsed)
        results = d.get("Results", [])
        techs: list[str] = []
        categories: dict[str, list[str]] = {}
        for result in results:
            for path in result.get("Result", {}).get("Paths", []):
                for tech in path.get("Technologies", []):
                    name = tech.get("Name", "")
                    cats = tech.get("Categories", [])
                    if name:
                        techs.append(name)
                    for cat in cats:
                        categories.setdefault(cat, []).append(name)
        finding = Finding(
            type="tech_stack",
            source="builtwith",
            url=f"https://builtwith.com/{target.normalized}",
            extracted={
                "domain":       target.normalized,
                "technologies": list(dict.fromkeys(techs))[:50],
                "categories":   {k: list(dict.fromkeys(v))[:10] for k, v in categories.items()},
                "tech_count":   len(set(techs)),
            },
            confidence=0.85,
        )
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=[finding], elapsed_ms=elapsed)


get_registry().register(BuiltWithConnector())
