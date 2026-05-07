"""linkedin2username wrapper — génère variations username depuis nom complet."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType, TargetNormalizer


class Linkedin2UsernameConnector(Connector):
    name = "linkedin2username"
    supports = {TargetType.PERSON_FULL}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("linkedin2username")

    async def query(self, target: Target):
        runner = get_runner()
        # Suppose target.normalized = "Firstname Lastname"
        parts = target.normalized.split()
        if len(parts) < 2:
            return fail(self.name, target, "needs first+last name", 0)
        firstname, lastname = parts[0], parts[-1]

        result = await runner.run(
            ["linkedin2username", "-c", lastname.lower(),
             "-n", firstname.lower(), "--no-banner"],
            timeout=20,
        )
        if not result.success and not result.stdout:
            # fallback : génération basique nous-même
            variations = self._fallback_variations(firstname, lastname)
        else:
            variations = []
            for line in result.stdout.splitlines():
                v = line.strip()
                if v and len(v) <= 30:
                    variations.append(v)

        findings: list[Finding] = []
        for v in variations[:20]:
            pivot = TargetNormalizer.detect(v)
            findings.append(Finding(
                type="username_variation",
                source="linkedin2username",
                extracted={"variation": v, "from_name": target.normalized},
                confidence=0.5,
                pivot_target=pivot if pivot.is_known else None,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)

    @staticmethod
    def _fallback_variations(firstname: str, lastname: str) -> list[str]:
        f, l = firstname.lower(), lastname.lower()
        return [
            f"{f}{l}", f"{f}.{l}", f"{f}_{l}", f"{f}-{l}",
            f"{f[0]}{l}", f"{l}{f}", f"{l}.{f}",
            f"{f}{l[0]}", f"{f}{l}1", f"{f}{l}99",
        ]


get_registry().register(Linkedin2UsernameConnector())
