"""Sherlock wrapper — username search 400+ sites."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok, parse_urls
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class SherlockConnector(Connector):
    name = "sherlock"
    supports = {TargetType.USERNAME, TargetType.PSEUDONYM, TargetType.INSTAGRAM_HANDLE}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("sherlock")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["sherlock", "--print-found", "--no-color", "--timeout", "8",
             "--folderoutput", "/tmp", target.normalized],
            timeout=180,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("[+]"):
                continue
            urls = parse_urls(line)
            if not urls:
                continue
            url = urls[0]
            site_part = line[3:].split(":", 1)[0].strip()
            findings.append(Finding(
                type="account",
                source=site_part or "unknown",
                url=url,
                extracted={"username": target.normalized, "site": site_part},
                confidence=0.9,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(SherlockConnector())
