"""Maigret wrapper — username search 3000+ sites (descendant Sherlock)."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class MaigretConnector(Connector):
    name = "maigret"
    supports = {TargetType.USERNAME, TargetType.PSEUDONYM, TargetType.INSTAGRAM_HANDLE}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("maigret")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["maigret", "--json", "ndjson", "--no-color", "--top-sites", "500",
             "--timeout", "8", target.normalized],
            timeout=240,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("status") != "found":
                continue
            site = obj.get("site_name") or obj.get("name") or "unknown"
            url = obj.get("url_user") or obj.get("url")
            findings.append(Finding(
                type="account",
                source=site,
                url=url,
                extracted={"username": target.normalized, "site": site,
                           "ids": obj.get("ids_data", {})},
                confidence=0.92,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(MaigretConnector())
