"""amass wrapper — OWASP subdomain enumeration."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class AmassConnector(Connector):
    name = "amass"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("amass")

    async def query(self, target: Target):
        runner = get_runner()
        # passive mode = pas de bruit DNS
        result = await runner.run(
            ["amass", "enum", "-passive", "-d", target.normalized, "-json", "/dev/stdout"],
            timeout=300,
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
            except json.JSONDecodeError:
                continue
            name = obj.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            findings.append(Finding(
                type="subdomain",
                source="amass",
                extracted={"subdomain": name, "domain": target.normalized,
                           "addresses": obj.get("addresses", [])},
                confidence=0.93,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(AmassConnector())
