"""
person_search_py — connecteur Python pour cibles PERSON_FULL.

Génère les username candidates depuis nom + prénom puis émet :
  - 1 Finding `username_candidates` listant TOUTES les permutations
    (`usernames` + `emails` champs structurés → cascade pivot lance ensuite
    sherlock / maigret / github_py / hibp / etc. sur chaque candidat).
  - N Findings `social_dork` (1 par profil trouvé via DDG dorks publics).

Cible : PERSON_FULL.   Aucune clé API requise.
"""
from __future__ import annotations
import re
import time
import unicodedata
import concurrent.futures as _cf
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.target import Target, TargetType


# ── name → username/email helpers ────────────────────────────────────────────
def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _slug(s: str) -> str:
    s = _ascii(s).lower()
    return re.sub(r"[^a-z0-9]", "", s)


_EMAIL_DOMAINS = ["gmail.com", "outlook.com", "hotmail.com", "yahoo.com",
                  "yahoo.fr", "proton.me", "icloud.com", "live.fr",
                  "free.fr", "laposte.net", "wanadoo.fr"]


def _generate_usernames(first: str, last: str, max_n: int = 16) -> list[str]:
    f, l = _slug(first), _slug(last)
    if not f or not l:
        return []
    cands: set[str] = {
        f + l, l + f, f + "." + l, f + "_" + l,
        f[:1] + l, f + l[:1], l[:1] + f, f, l,
    }
    cands |= {c + str(n) for c in list(cands) for n in (1, 7, 23, 99)}
    out = sorted(c for c in cands if c and 3 <= len(c) <= 30)
    return out[:max_n]


def _generate_emails(first: str, last: str, max_n: int = 30) -> list[str]:
    f, l = _slug(first), _slug(last)
    if not f or not l:
        return []
    locals_ = {f + "." + l, f + l, f[:1] + l, f + "." + l[:1], l + "." + f}
    out = [f"{lp}@{d}" for lp in locals_ for d in _EMAIL_DOMAINS]
    return out[:max_n]


_SOCIAL_DORKS = {
    "linkedin":     'site:linkedin.com/in "{q}"',
    "facebook":     'site:facebook.com "{q}"',
    "instagram":    'site:instagram.com "{q}"',
    "twitter":      '(site:twitter.com OR site:x.com) "{q}"',
    "github":       'site:github.com "{q}"',
    "tiktok":       'site:tiktok.com "{q}"',
    "youtube":      'site:youtube.com "{q}"',
    "viadeo":       'site:viadeo.com "{q}"',
    "researchgate": 'site:researchgate.net "{q}"',
}


def _ddg(query: str, n: int = 3) -> list[dict]:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return [
                {"title": r.get("title", ""),
                 "snippet": r.get("body", ""),
                 "url": r.get("href", "")}
                for r in ddgs.text(query, max_results=n)
            ]
    except Exception:
        return []


# ── connector ─────────────────────────────────────────────────────────────────
class PersonSearchConnector(Connector):
    name         = "person_search_py"
    supports     = {TargetType.PERSON_FULL}
    requires_key = False
    rate_limit   = 60
    backend      = "python"

    def is_available(self) -> bool:
        return True  # DDG facultatif, génération username toujours dispo

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        full = target.normalized.strip()
        parts = full.split()
        if len(parts) < 2:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="person_search: nom incomplet (besoin prénom + nom)",
                elapsed_ms=int((time.monotonic() - t0) * 1000),
            )
        first = parts[0]
        last  = " ".join(parts[1:])

        usernames = _generate_usernames(first, last)
        emails    = _generate_emails(first, last)

        findings: list[Finding] = []

        # 1) Finding pivot — username/email candidates → cascade pivot relaie
        if usernames or emails:
            findings.append(Finding(
                type="username_candidates",
                source="person_search_py",
                extracted={
                    "person":    full,
                    "first":     first,
                    "last":      last,
                    "usernames": usernames,
                    "emails":    emails,
                },
                confidence=0.7,
            ))

        # 2) Dorks DDG sur les réseaux sociaux (parallèle, 4 workers)
        try:
            with _cf.ThreadPoolExecutor(max_workers=4) as ex:
                futs = {
                    ex.submit(_ddg, tpl.format(q=full), 3): site
                    for site, tpl in _SOCIAL_DORKS.items()
                }
                for fut in _cf.as_completed(futs, timeout=20):
                    site = futs[fut]
                    try:
                        results = fut.result()
                    except Exception:
                        continue
                    for r in results:
                        url = r.get("url", "")
                        if not url:
                            continue
                        findings.append(Finding(
                            type="social_dork",
                            source=f"ddg/{site}",
                            url=url,
                            extracted={
                                "person":  full,
                                "site":    site,
                                "title":   r.get("title", "")[:200],
                                "snippet": r.get("snippet", "")[:300],
                                "url":     url,
                            },
                            confidence=0.55,
                        ))
        except Exception:
            pass

        elapsed = int((time.monotonic() - t0) * 1000)
        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
        )


get_registry().register(PersonSearchConnector())
