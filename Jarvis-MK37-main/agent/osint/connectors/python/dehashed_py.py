"""
Dehashed — recherche dans les bases de données leakées.
Cibles : EMAIL, USERNAME | clé DEHASHED_KEY + email compte requis.
Auth : HTTP Basic (email:api_key).
"""
from __future__ import annotations
import base64, os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV   = "DEHASHED_KEY"
_EMAIL_ENV = "DEHASHED_EMAIL"
_BASE      = "https://api.dehashed.com"


class DehashedConnector(Connector):
    name         = "dehashed_py"
    supports     = {TargetType.EMAIL, TargetType.USERNAME}
    requires_key = True
    rate_limit   = 5
    backend      = "python"

    def _creds(self) -> tuple[str, str]:
        return os.environ.get(_EMAIL_ENV, ""), os.environ.get(_KEY_ENV, "")

    def is_available(self) -> bool:
        e, k = self._creds()
        return bool(e and k)

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        email, key = self._creds()
        if not (email and key):
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="DEHASHED_EMAIL + DEHASHED_KEY required", elapsed_ms=0)
        cred = base64.b64encode(f"{email}:{key}".encode()).decode()
        field = "email" if target.type == TargetType.EMAIL else "username"
        resp = await async_get(f"{_BASE}/search",
                               params={"query": f'{field}:"{target.normalized}"', "size": 20},
                               headers={"Authorization": f"Basic {cred}",
                                        "Accept": "application/json"},
                               timeout=15.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"dehashed {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        if not isinstance(d, dict):
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        findings: list[Finding] = []
        for entry in d.get("entries", []) or []:
            findings.append(Finding(
                type="leak_credential",
                source="dehashed",
                extracted={
                    "target":    target.normalized,
                    "email":     entry.get("email", ""),
                    "username":  entry.get("username", ""),
                    "password":  entry.get("password", ""),
                    "hashed_pw": entry.get("hashed_password", ""),
                    "name":      entry.get("name", ""),
                    "database":  entry.get("database_name", ""),
                    "address":   entry.get("address", ""),
                    "phone":     entry.get("phone", ""),
                    "ip":        entry.get("ip_address", ""),
                },
                confidence=0.8,
            ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed)


get_registry().register(DehashedConnector())
