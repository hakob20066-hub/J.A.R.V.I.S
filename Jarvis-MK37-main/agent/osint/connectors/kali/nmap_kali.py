"""nmap wrapper — light port/service scan (top 100 ports, no OS detect)."""
from __future__ import annotations
import re

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


PORT_LINE = re.compile(r"^(\d+)/(\w+)\s+(\w+)\s+(.+)$")


class NmapConnector(Connector):
    name = "nmap"
    supports = {TargetType.IP, TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30  # respectful scanning

    def is_available(self) -> bool:
        return get_runner().is_tool_available("nmap")

    async def query(self, target: Target):
        runner = get_runner()
        # -F = top 100 ports, -sV light service detect, -T4 reasonable speed
        result = await runner.run(
            ["nmap", "-F", "-sV", "-T4", "--max-retries", "1", target.normalized],
            timeout=180,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            m = PORT_LINE.match(line)
            if not m:
                continue
            port, proto, state, service = m.groups()
            if state.lower() != "open":
                continue
            findings.append(Finding(
                type="port",
                source="nmap",
                extracted={"port": int(port), "proto": proto,
                           "service": service.strip(), "host": target.normalized},
                confidence=0.95,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(NmapConnector())
