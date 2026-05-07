"""
PivotEngine — extrait nouvelles cibles depuis findings.

Voir [[14-Phases/phase7.6-pivot-cascade]].

Chaque finding peut contenir des données qui sont à leur tour des cibles OSINT
(email trouvé dans bio Instagram, domain dans github profile, etc.).
"""
from __future__ import annotations

import re
from typing import Iterable

from agent.osint.connectors.base import Finding
from agent.osint.target import Target, TargetNormalizer, TargetType


# Champs typiquement pivotables dans Finding.extracted
PIVOT_FIELDS = (
    "email", "emails",
    "username", "usernames", "handle", "handles", "alias",
    "domain", "domains", "website", "websites", "url", "urls",
    "phone", "phones",
    "ip", "ips",
    "person", "name", "fullname", "full_name",
    "address", "addresses",
    "btc", "eth", "wallet", "wallets",
    "image_url", "profile_pic", "avatar",
)


class PivotEngine:
    """Extrait des Targets depuis les Findings."""

    def __init__(self, max_pivots_per_finding: int = 5):
        self.max_pivots_per_finding = max_pivots_per_finding

    def extract_pivots(self, finding: Finding) -> list[Target]:
        """
        Renvoie une liste de Targets dérivés d'un Finding.
        Évite les doublons par normalized form.
        """
        targets: list[Target] = []
        seen: set[str] = set()

        # 1) pivot_target explicite (le connecteur a déjà identifié un pivot)
        if finding.pivot_target and finding.pivot_target.is_known:
            key = f"{finding.pivot_target.type.value}:{finding.pivot_target.normalized}"
            if key not in seen:
                seen.add(key)
                targets.append(finding.pivot_target)

        # 2) Champs structurés dans extracted
        for field, value in (finding.extracted or {}).items():
            if field not in PIVOT_FIELDS:
                continue
            for raw in self._iter_values(value):
                t = TargetNormalizer.detect(raw)
                if not t.is_known or t.confidence < 0.5:
                    continue
                key = f"{t.type.value}:{t.normalized}"
                if key in seen:
                    continue
                seen.add(key)
                targets.append(t)
                if len(targets) >= self.max_pivots_per_finding:
                    return targets

        # 3) URL → domain extract
        if finding.url and len(targets) < self.max_pivots_per_finding:
            m = re.match(r"https?://([^/]+)", finding.url)
            if m:
                t = TargetNormalizer.detect(m.group(1))
                if t.is_known and t.type == TargetType.DOMAIN:
                    key = f"{t.type.value}:{t.normalized}"
                    if key not in seen:
                        targets.append(t)

        return targets

    @staticmethod
    def _iter_values(value) -> Iterable[str]:
        if value is None:
            return
        if isinstance(value, str):
            yield value
        elif isinstance(value, (list, tuple, set)):
            for v in value:
                if isinstance(v, str):
                    yield v
        elif isinstance(value, dict):
            for v in value.values():
                if isinstance(v, str):
                    yield v
