"""dnsenum wrapper — DNS enumeration (NS, MX, A, brute subdomains)."""
from __future__ import annotations
import re

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok, parse_domains
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


HOST_LINE = re.compile(r"^\s*([a-z0-9\-.]+)\.\s+\d+\s+IN\s+(A|AAAA|MX|NS|CNAME|TXT)\s+(.+)$",
                       re.IGNORECASE)


class DnsenumConnector(Connector):
    name = "dnsenum"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("dnsenum")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["dnsenum", "--noreverse", "--nocolor", "--threads", "5", target.normalized],
            timeout=300,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            m = HOST_LINE.match(line)
            if m:
                host, rtype, value = m.groups()
                key = f"{host}|{rtype}|{value}"
                if key in seen:
                    continue
                seen.add(key)
                findings.append(Finding(
                    type="dns_record",
                    source="dnsenum",
                    extracted={"host": host, "type": rtype, "value": value.strip()},
                    confidence=0.9,
                ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(DnsenumConnector())
