"""nuclei wrapper — templates-based vulnerability scanner."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class NucleiConnector(Connector):
    name = "nuclei"
    supports = {TargetType.DOMAIN, TargetType.IP}
    backend = "kali"
    requires_key = False
    rate_limit = 12

    def is_available(self) -> bool:
        return get_runner().is_tool_available("nuclei")

    async def query(self, target: Target):
        runner = get_runner()
        url = target.normalized if target.normalized.startswith("http") \
              else f"https://{target.normalized}"
        # -severity info,low : reste passif
        result = await runner.run(
            ["nuclei", "-u", url, "-jsonl", "-silent",
             "-severity", "info,low,medium,high,critical",
             "-rate-limit", "30"],
            timeout=300,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines()[:100]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            info = obj.get("info", {})
            findings.append(Finding(
                type="vulnerability",
                source="nuclei",
                url=obj.get("matched-at"),
                extracted={
                    "template":  obj.get("template-id"),
                    "name":      info.get("name"),
                    "severity":  info.get("severity"),
                    "tags":      info.get("tags"),
                    "matched":   obj.get("matched-at"),
                },
                confidence=0.92,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(NucleiConnector())
