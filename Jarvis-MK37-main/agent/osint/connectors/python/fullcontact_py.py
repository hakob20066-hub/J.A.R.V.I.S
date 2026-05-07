"""
FullContact — enrichissement email → fiche personne (nom, photo, réseaux).
Cibles : EMAIL | clé FC_API_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "FC_API_KEY"
_BASE    = "https://api.fullcontact.com/v3"


class FullContactConnector(Connector):
    name         = "fullcontact_py"
    supports     = {TargetType.EMAIL}
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
                                   error="FC_API_KEY not set", elapsed_ms=0)
        # FullContact v3 utilise POST
        import json as _json
        from agent.osint.connectors.python._http import _sync_get
        # Async POST via httpx
        try:
            import httpx
            t_start = time.monotonic()
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(
                    f"{_BASE}/person.enrich",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    content=_json.dumps({"email": target.normalized}).encode(),
                )
            elapsed = int((time.monotonic() - t_start) * 1000)
            if r.status_code == 404:
                return ConnectorResult(connector=self.name, target=target, success=True,
                                       findings=[], elapsed_ms=elapsed)
            if not r.is_success:
                return ConnectorResult(connector=self.name, target=target, success=False,
                                       error=f"fullcontact {r.status_code}: {r.text[:120]}",
                                       elapsed_ms=elapsed)
            d = r.json()
        except ImportError:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="httpx required for FullContact POST", elapsed_ms=0)
        except Exception as e:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=str(e), elapsed_ms=int((time.monotonic()-t0)*1000))

        name_obj = d.get("fullName", "") or ""
        socials  = {s.get("type", ""): s.get("url", "")
                    for s in d.get("socialProfiles", []) if isinstance(s, dict)}
        finding = Finding(
            type="person_profile",
            source="fullcontact",
            extracted={
                "email":       target.normalized,
                "full_name":   name_obj,
                "age_range":   d.get("ageRange", ""),
                "gender":      d.get("gender", ""),
                "location":    d.get("location", ""),
                "bio":         d.get("bio", ""),
                "avatar":      d.get("avatar", ""),
                "linkedin":    socials.get("linkedin", ""),
                "twitter":     socials.get("twitter", ""),
                "facebook":    socials.get("facebook", ""),
                "employment":  [e.get("name", "") for e in d.get("employment", [])[:3]],
                "education":   [e.get("name", "") for e in d.get("education", [])[:3]],
            },
            confidence=0.82,
        )
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=[finding], elapsed_ms=elapsed)


get_registry().register(FullContactConnector())
