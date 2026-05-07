"""twint wrapper — Twitter scraping (deprecated mais toujours dans Kali)."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class TwintConnector(Connector):
    name = "twint"
    supports = {TargetType.SOCIAL_HANDLE, TargetType.USERNAME, TargetType.PSEUDONYM}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("twint")

    async def query(self, target: Target):
        runner = get_runner()
        out_path = f"/tmp/twint_{target.hash()}.json"
        result = await runner.run(
            ["twint", "-u", target.normalized, "--limit", "50",
             "-o", out_path, "--json"],
            timeout=120,
        )
        cat = await runner.run(["cat", out_path], timeout=5)
        if not cat.success:
            return fail(self.name, target, "twint no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in cat.stdout.splitlines()[:50]:
            line = line.strip()
            if not line:
                continue
            try:
                tweet = json.loads(line)
            except json.JSONDecodeError:
                continue
            findings.append(Finding(
                type="tweet",
                source="twitter",
                url=tweet.get("link"),
                extracted={"username": target.normalized,
                           "tweet": (tweet.get("tweet") or "")[:280],
                           "date": tweet.get("date"),
                           "language": tweet.get("language"),
                           "place": tweet.get("place"),
                           "mentions": tweet.get("mentions", []),
                           "hashtags": tweet.get("hashtags", [])},
                confidence=0.9,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(TwintConnector())
