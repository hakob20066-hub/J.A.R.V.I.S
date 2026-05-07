"""gitleaks wrapper — secrets dans git history."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class GitleaksConnector(Connector):
    name = "gitleaks"
    supports = {TargetType.DOMAIN}  # used on github.com URLs
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("gitleaks")

    async def query(self, target: Target):
        runner = get_runner()
        # Suppose target is a github URL ou domain → on tente clone shallow + scan
        if "github.com" not in target.normalized.lower():
            return fail(self.name, target, "gitleaks needs a github URL", 0)
        repo_url = target.normalized if target.normalized.startswith("http") \
                   else f"https://{target.normalized}"
        clone_dir = f"/tmp/gl_{target.hash()}"
        await runner.run(["git", "clone", "--depth", "50", repo_url, clone_dir],
                         timeout=60)
        result = await runner.run(
            ["gitleaks", "detect", "--source", clone_dir, "--report-format", "json",
             "--report-path", "/tmp/gitleaks_report.json", "--no-banner"],
            timeout=120,
        )
        cat = await runner.run(["cat", "/tmp/gitleaks_report.json"], timeout=5)
        findings: list[Finding] = []
        if cat.success:
            try:
                data = json.loads(cat.stdout)
                for leak in (data or [])[:50]:
                    findings.append(Finding(
                        type="git_secret",
                        source="gitleaks",
                        extracted={"rule": leak.get("RuleID"),
                                   "file": leak.get("File"),
                                   "commit": leak.get("Commit"),
                                   "match": leak.get("Match", "")[:100]},
                        confidence=0.9,
                    ))
            except json.JSONDecodeError:
                pass
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(GitleaksConnector())
