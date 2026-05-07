"""trufflehog wrapper — secrets scanner avancé (gitleaks alternative)."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class TruffleHogConnector(Connector):
    name = "trufflehog"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("trufflehog")

    async def query(self, target: Target):
        runner = get_runner()
        if "github.com" not in target.normalized.lower():
            return fail(self.name, target, "trufflehog needs github URL", 0)
        repo_url = target.normalized if target.normalized.startswith("http") \
                   else f"https://{target.normalized}"
        result = await runner.run(
            ["trufflehog", "git", repo_url, "--json", "--no-update"],
            timeout=180,
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
            findings.append(Finding(
                type="git_secret",
                source="trufflehog",
                extracted={
                    "detector": obj.get("DetectorName"),
                    "verified": obj.get("Verified"),
                    "raw":      str(obj.get("Raw", ""))[:100],
                    "source":   obj.get("SourceMetadata", {}),
                },
                confidence=0.95 if obj.get("Verified") else 0.7,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(TruffleHogConnector())
