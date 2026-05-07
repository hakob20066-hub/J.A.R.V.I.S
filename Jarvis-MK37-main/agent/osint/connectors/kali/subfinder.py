"""subfinder wrapper — fast passive subdomain enum (ProjectDiscovery)."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class SubfinderConnector(Connector):
    name = "subfinder"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("subfinder")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["subfinder", "-d", target.normalized, "-silent", "-oJ"],
            timeout=180,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                host = obj.get("host")
            except json.JSONDecodeError:
                host = line  # silent mode peut juste sortir le host
            if not host or host in seen:
                continue
            seen.add(host)
            findings.append(Finding(
                type="subdomain",
                source="subfinder",
                extracted={"subdomain": host, "domain": target.normalized},
                confidence=0.9,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(SubfinderConnector())
