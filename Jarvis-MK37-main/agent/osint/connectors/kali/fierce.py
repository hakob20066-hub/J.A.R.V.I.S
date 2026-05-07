"""fierce wrapper — DNS recon agressif."""
from __future__ import annotations
import re

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


HOST_LINE = re.compile(r"^([\w.\-]+)\s+\.\s+\d+\s+IN\s+A\s+([\d.]+)$", re.MULTILINE)
FOUND_LINE = re.compile(r"^Found:\s+([\w.\-]+)\.\s+\(([\d.]+)\)$", re.MULTILINE)


class FierceConnector(Connector):
    name = "fierce"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 20

    def is_available(self) -> bool:
        return get_runner().is_tool_available("fierce")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(["fierce", "--domain", target.normalized],
                                  timeout=180)
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        seen: set[str] = set()
        for m in FOUND_LINE.finditer(result.stdout):
            host, ip = m.group(1), m.group(2)
            if host in seen:
                continue
            seen.add(host)
            findings.append(Finding(
                type="subdomain",
                source="fierce",
                extracted={"subdomain": host, "ip": ip, "domain": target.normalized},
                confidence=0.88,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(FierceConnector())
