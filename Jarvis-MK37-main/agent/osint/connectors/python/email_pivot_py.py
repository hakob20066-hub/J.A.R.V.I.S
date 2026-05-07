"""
email_pivot_py — extrait des username candidates depuis un email.

Émet un Finding `email_pivot` avec :
  - `usernames` : variations du local part (avec/sans points, chiffres…)
  - `domain`    : domaine partie droite (sauf providers grand public)

→ La cascade pivot transforme ces champs en targets USERNAME / DOMAIN
  qui sont ensuite traités par sherlock, maigret, github_py, holehe, etc.

Toujours disponible (pas de clé, pas de réseau) → garantit que la cascade
trouve TOUJOURS des sous-cibles à explorer même si les autres connecteurs
email échouent par défaut de clé API.
"""
from __future__ import annotations
import re
import time

from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.target import Target, TargetType


# Domaines grand public — on n'émet pas le domain comme pivot
# (gmail.com, hotmail.com sont sans intérêt OSINT)
_PUBLIC_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "live.fr", "yahoo.com", "yahoo.fr", "icloud.com", "me.com", "mac.com",
    "proton.me", "protonmail.com", "tutanota.com", "gmx.com", "gmx.fr",
    "free.fr", "orange.fr", "wanadoo.fr", "laposte.net", "sfr.fr", "neuf.fr",
    "aol.com", "mail.com", "zoho.com", "yandex.com", "yandex.ru",
}


def _username_variations(local: str) -> list[str]:
    """Génère des variations username plausibles depuis le local part."""
    out: set[str] = set()
    base = local.strip().lower()
    if not base:
        return []
    out.add(base)

    # Sans séparateurs (.−_)
    no_sep = re.sub(r"[._\-]", "", base)
    if no_sep and len(no_sep) >= 3:
        out.add(no_sep)

    # Sans chiffres en suffixe (foo123 → foo)
    no_suffix_num = re.sub(r"\d+$", "", base)
    if no_suffix_num and len(no_suffix_num) >= 3 and no_suffix_num != base:
        out.add(no_suffix_num)
    no_sep_no_num = re.sub(r"\d+$", "", no_sep)
    if no_sep_no_num and len(no_sep_no_num) >= 3:
        out.add(no_sep_no_num)

    # Si email contient un point (prenom.nom@…) → garder les parties séparément
    parts = [p for p in re.split(r"[._\-]", base) if len(p) >= 3]
    for p in parts:
        out.add(p)
        # part sans chiffre suffixe
        clean = re.sub(r"\d+$", "", p)
        if clean and len(clean) >= 3:
            out.add(clean)

    # Filtre final :
    # - 3 ≤ len ≤ 30
    # - alphanum + . _ - uniquement
    # - pas commencer/finir par .-_
    # - au moins une lettre (élimine "20066", "1234")
    valid = []
    for u in out:
        u = u.strip("._-")
        if not (3 <= len(u) <= 30):
            continue
        if not re.match(r"^[a-z0-9._\-]+$", u):
            continue
        if not any(c.isalpha() for c in u):
            continue
        valid.append(u)
    return sorted(set(valid))


class EmailPivotConnector(Connector):
    name         = "email_pivot_py"
    supports     = {TargetType.EMAIL}
    requires_key = False
    rate_limit   = 999      # purement local
    backend      = "python"

    def is_available(self) -> bool:
        return True

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        email = target.normalized
        if "@" not in email:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="email_pivot: invalid email", elapsed_ms=0,
            )
        local, _, domain = email.partition("@")
        usernames = _username_variations(local)

        extracted = {
            "email":     email,
            "local":     local,
            "usernames": usernames,
        }
        if domain and domain.lower() not in _PUBLIC_MAIL_DOMAINS:
            extracted["domain"] = domain.lower()

        finding = Finding(
            type="email_pivot",
            source="email_pivot_py",
            extracted=extracted,
            confidence=0.6,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=[finding], elapsed_ms=elapsed,
        )


get_registry().register(EmailPivotConnector())
