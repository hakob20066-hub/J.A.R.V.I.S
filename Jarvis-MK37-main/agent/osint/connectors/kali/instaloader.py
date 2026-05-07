"""instaloader wrapper — Instagram profile scraping (anonymous)."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class InstaloaderConnector(Connector):
    name = "instaloader"
    supports = {TargetType.INSTAGRAM_HANDLE}
    backend = "kali"
    requires_key = False
    rate_limit = 30   # IG anti-bot strict

    def is_available(self) -> bool:
        return get_runner().is_tool_available("instaloader")

    async def query(self, target: Target):
        runner = get_runner()
        # --no-pictures = pas de download images, juste metadata profile
        result = await runner.run(
            ["instaloader", "--no-pictures", "--no-videos", "--no-video-thumbnails",
             "--no-captions", "--no-metadata-json", "--quiet",
             "--", target.normalized],
            timeout=60,
        )
        if not result.success:
            return fail(self.name, target,
                        result.stderr[:200] if result.stderr else "instaloader failed",
                        result.elapsed_ms)

        findings: list[Finding] = []
        # Profile JSON
        prof_path = f"/tmp/{target.normalized}/{target.normalized}_id.txt"
        cat = await runner.run(["cat", prof_path], timeout=5)
        if cat.success and cat.stdout.strip():
            findings.append(Finding(
                type="profile",
                source="instagram",
                url=f"https://instagram.com/{target.normalized}/",
                extracted={"username": target.normalized,
                           "instagram_id": cat.stdout.strip()},
                confidence=0.95,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(InstaloaderConnector())
