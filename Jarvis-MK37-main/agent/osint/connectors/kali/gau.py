"""gau (GetAllUrls) wrapper — URLs depuis Wayback + AlienVault + CommonCrawl."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class GauConnector(Connector):
    name = "gau"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("gau")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["gau", "--threads", "5", "--blacklist", "css,jpg,jpeg,png,gif,svg",
             target.normalized],
            timeout=180,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines()[:500]:
            url = line.strip()
            if not url or url in seen or not url.startswith("http"):
                continue
            seen.add(url)
            findings.append(Finding(
                type="historical_url",
                source="gau",
                url=url,
                extracted={"url": url, "domain": target.normalized},
                confidence=0.75,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(GauConnector())
