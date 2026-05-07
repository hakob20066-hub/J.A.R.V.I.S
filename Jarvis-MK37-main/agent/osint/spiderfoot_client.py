"""
SpiderFoot client — daemon REST API à la demande.

Voir [[14-Phases/phase7.6-spiderfoot-client]].
Décision lock : daemon lancé au 1er OSINT, pas au boot Jarvis.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

import requests

from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


SPIDERFOOT_HOST = "127.0.0.1"
SPIDERFOOT_PORT = 5001
SPIDERFOOT_BASE = f"http://{SPIDERFOOT_HOST}:{SPIDERFOOT_PORT}"

# Mapping TargetType → SpiderFoot type query string
SF_TYPE_MAP = {
    TargetType.EMAIL:            "EMAILADDR",
    TargetType.DOMAIN:           "INTERNET_NAME",
    TargetType.IP:               "IP_ADDRESS",
    TargetType.USERNAME:         "USERNAME",
    TargetType.PSEUDONYM:        "USERNAME",
    TargetType.INSTAGRAM_HANDLE: "USERNAME",
    TargetType.PHONE:            "PHONE_NUMBER",
}


class SpiderFootClient:
    """Wrapper REST API SpiderFoot."""

    def __init__(self, base_url: str = SPIDERFOOT_BASE):
        self.base_url = base_url
        self._daemon_started = False

    async def _ensure_running(self) -> bool:
        """Vérifie daemon up, lance via kali_runner sinon. Best-effort."""
        if self._is_alive():
            return True
        runner = get_runner()
        if not runner.is_tool_available("spiderfoot"):
            return False
        # Lance en background détaché (subprocess Popen via shell)
        cmd = ["nohup", "spiderfoot", "-l", f"{SPIDERFOOT_HOST}:{SPIDERFOOT_PORT}",
               "&"]
        # On ne await pas (daemon doit tourner ad vitam)
        try:
            await runner.run(["sh", "-c",
                              f"nohup spiderfoot -l {SPIDERFOOT_HOST}:{SPIDERFOOT_PORT} "
                              f">/tmp/spiderfoot.log 2>&1 &"], timeout=5)
        except Exception:
            pass
        # Wait up to 8s for daemon
        for _ in range(16):
            await asyncio.sleep(0.5)
            if self._is_alive():
                self._daemon_started = True
                return True
        return False

    def _is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/ping", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    async def list_modules(self) -> list[dict]:
        if not self._is_alive():
            return []
        try:
            r = requests.get(f"{self.base_url}/modules", timeout=10)
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []

    async def scan(self, target: Target, modules: Optional[list[str]] = None,
                   timeout: int = 240) -> list[dict]:
        """Lance un scan, attend complétion, retourne les events."""
        if not await self._ensure_running():
            return []

        sf_type = SF_TYPE_MAP.get(target.type)
        if not sf_type:
            return []

        # Start scan
        payload = {
            "scanname":   f"jarvis_{target.hash()}",
            "scantarget": target.normalized,
            "usecase":    "all" if not modules else "passive",
            "modulelist": ",".join(f"module_{m}" for m in modules) if modules else "",
            "typelist":   sf_type,
        }
        try:
            r = requests.post(f"{self.base_url}/startscan", data=payload, timeout=10)
            if r.status_code != 200:
                return []
            scan_id = r.text.strip().strip('"')
        except Exception:
            return []

        # Poll status
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.base_url}/scanstatus", params={"id": scan_id}, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    status = data[5] if isinstance(data, list) and len(data) > 5 else None
                    if status in ("FINISHED", "ABORTED", "ERROR-FAILED"):
                        break
            except Exception:
                pass
            await asyncio.sleep(2.0)

        # Fetch results
        try:
            r = requests.get(f"{self.base_url}/scaneventresults",
                             params={"id": scan_id}, timeout=15)
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []


class SpiderFootConnector(Connector):
    """1 connecteur, 200+ modules SpiderFoot derrière."""
    name = "spiderfoot"
    supports = {TargetType.EMAIL, TargetType.DOMAIN, TargetType.IP,
                TargetType.USERNAME, TargetType.PSEUDONYM,
                TargetType.INSTAGRAM_HANDLE, TargetType.PHONE}
    backend = "kali"
    requires_key = False
    rate_limit = 12  # lourd, on limite

    def __init__(self):
        self.client = SpiderFootClient()

    def is_available(self) -> bool:
        return get_runner().is_tool_available("spiderfoot")

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.perf_counter()
        events = await self.client.scan(target)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if not events:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   findings=[], elapsed_ms=elapsed_ms,
                                   error="spiderfoot returned no events")

        findings: list[Finding] = []
        for ev in events:
            # SpiderFoot event format : [generated, data, source, type, ...]
            if not isinstance(ev, (list, tuple)) or len(ev) < 4:
                continue
            data = ev[1]
            source = ev[2]
            event_type = ev[3]
            findings.append(Finding(
                type=event_type.lower(),
                source=f"spiderfoot:{source}",
                extracted={"data": str(data)[:500], "module": source},
                confidence=0.8,
            ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed_ms)


_CLIENT_SINGLETON: Optional[SpiderFootClient] = None


def get_spiderfoot_client() -> SpiderFootClient:
    global _CLIENT_SINGLETON
    if _CLIENT_SINGLETON is None:
        _CLIENT_SINGLETON = SpiderFootClient()
    return _CLIENT_SINGLETON


get_registry().register(SpiderFootConnector())
