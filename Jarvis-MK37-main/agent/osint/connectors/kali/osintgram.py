"""osintgram wrapper — Instagram OSINT plus profond qu'instaloader."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok, parse_emails
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class OsintgramConnector(Connector):
    name = "osintgram"
    supports = {TargetType.INSTAGRAM_HANDLE}
    backend = "kali"
    requires_key = True   # nécessite credentials IG dans config/osintgram
    rate_limit = 20

    def is_available(self) -> bool:
        return get_runner().is_tool_available("osintgram")

    async def query(self, target: Target):
        runner = get_runner()
        # Modes utiles : info, captions, emails, fwersemail, locations, hashtags
        findings: list[Finding] = []
        total_ms = 0

        for mode in ("info", "emails", "captions"):
            r = await runner.run(
                ["osintgram", target.normalized, "-c", mode, "-o", "/tmp/og"],
                timeout=120,
            )
            total_ms += r.elapsed_ms
            if not r.success:
                continue

            if mode == "emails":
                for email in parse_emails(r.stdout):
                    findings.append(Finding(
                        type="email",
                        source="osintgram:instagram",
                        extracted={"email": email, "instagram": target.normalized},
                        confidence=0.85,
                    ))
            elif mode == "info":
                findings.append(Finding(
                    type="profile",
                    source="instagram",
                    url=f"https://instagram.com/{target.normalized}/",
                    extracted={"info": r.stdout[:1000],
                               "username": target.normalized},
                    confidence=0.9,
                ))
            elif mode == "captions":
                # captions souvent contiennent emails/handles → pivots
                findings.append(Finding(
                    type="captions",
                    source="instagram",
                    extracted={"captions_preview": r.stdout[:2000],
                               "username": target.normalized},
                    confidence=0.7,
                ))
        return ok(self.name, target, findings, total_ms)


get_registry().register(OsintgramConnector())
