"""
username_scan_py — équivalent Python natif de Sherlock.

Vérifie l'existence d'un username sur 18 plateformes via HEAD/GET requests.
Aucune clé API, aucun outil Kali requis. Fonctionne sur Windows out-of-the-box.

Cible : USERNAME, PSEUDONYM, INSTAGRAM_HANDLE.
"""
from __future__ import annotations
import asyncio
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.target import Target, TargetType


# Catalogue de sites — {nom: (url_template, status_codes_si_existe)}
# Pour la plupart : 200 = compte existe, 404 = n'existe pas
# Certains sites renvoient 200 même pour "user not found" → on regarde le contenu
_SITES: dict[str, dict] = {
    "GitHub":     {"url": "https://github.com/{u}",                  "ok": (200,)},
    "GitLab":     {"url": "https://gitlab.com/{u}",                  "ok": (200,)},
    "Twitter/X":  {"url": "https://x.com/{u}",                       "ok": (200,)},
    "Instagram":  {"url": "https://www.instagram.com/{u}/",          "ok": (200,)},
    "TikTok":     {"url": "https://www.tiktok.com/@{u}",             "ok": (200,)},
    "Reddit":     {"url": "https://www.reddit.com/user/{u}",         "ok": (200,)},
    "Twitch":     {"url": "https://www.twitch.tv/{u}",               "ok": (200,)},
    "YouTube":    {"url": "https://www.youtube.com/@{u}",            "ok": (200,)},
    "Pinterest":  {"url": "https://www.pinterest.com/{u}/",          "ok": (200,)},
    "Steam":      {"url": "https://steamcommunity.com/id/{u}",       "ok": (200,)},
    "Keybase":    {"url": "https://keybase.io/{u}",                  "ok": (200,)},
    "Medium":     {"url": "https://medium.com/@{u}",                 "ok": (200,)},
    "Dev.to":     {"url": "https://dev.to/{u}",                      "ok": (200,)},
    "Vimeo":      {"url": "https://vimeo.com/{u}",                   "ok": (200,)},
    "Flickr":     {"url": "https://www.flickr.com/people/{u}",       "ok": (200,)},
    "SoundCloud": {"url": "https://soundcloud.com/{u}",              "ok": (200,)},
    "Roblox":     {"url": "https://www.roblox.com/user.aspx?username={u}", "ok": (200,)},
    "About.me":   {"url": "https://about.me/{u}",                    "ok": (200,)},
}


class UsernameScanConnector(Connector):
    name         = "username_scan_py"
    supports     = {TargetType.USERNAME, TargetType.PSEUDONYM, TargetType.INSTAGRAM_HANDLE}
    requires_key = False
    rate_limit   = 60
    backend      = "python"

    def is_available(self) -> bool:
        try:
            import httpx  # noqa
            return True
        except ImportError:
            try:
                import requests  # noqa
                return True
            except ImportError:
                return False

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        username = target.normalized.lstrip("@").strip()
        if not username or len(username) < 3:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"username_scan: invalid username {username!r}",
                elapsed_ms=0,
            )

        findings: list[Finding] = []
        try:
            import httpx
            results = await self._scan_httpx(username)
        except ImportError:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self._scan_requests, username
            )

        for site, url, found in results:
            if found:
                findings.append(Finding(
                    type="account",
                    source=f"username_scan/{site.lower()}",
                    url=url,
                    extracted={
                        "site":     site,
                        "username": username,
                        "url":      url,
                    },
                    confidence=0.85,
                ))

        elapsed = int((time.monotonic() - t0) * 1000)
        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
        )

    # ─── async (httpx) ────────────────────────────────────────────────────────
    async def _scan_httpx(self, username: str) -> list[tuple[str, str, bool]]:
        import httpx
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JARVIS-OSINT/1.0)"}
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=6.0, headers=headers
        ) as client:
            tasks = [
                self._check_one_httpx(client, site, cfg, username)
                for site, cfg in _SITES.items()
            ]
            return await asyncio.gather(*tasks, return_exceptions=False)

    @staticmethod
    async def _check_one_httpx(client, site: str, cfg: dict, username: str) -> tuple[str, str, bool]:
        url = cfg["url"].format(u=username)
        ok_codes = cfg.get("ok", (200,))
        try:
            r = await client.head(url)
            if r.status_code in (403, 405, 501):
                # certains sites bloquent HEAD → essai GET partiel
                r = await client.get(url)
            return (site, url, r.status_code in ok_codes)
        except Exception:
            return (site, url, False)

    # ─── sync (requests fallback) ─────────────────────────────────────────────
    @staticmethod
    def _scan_requests(username: str) -> list[tuple[str, str, bool]]:
        import requests
        import concurrent.futures as _cf
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JARVIS-OSINT/1.0)"}

        def _check(site: str, cfg: dict) -> tuple[str, str, bool]:
            url = cfg["url"].format(u=username)
            ok_codes = cfg.get("ok", (200,))
            try:
                r = requests.head(url, headers=headers, timeout=6.0,
                                  allow_redirects=True)
                if r.status_code in (403, 405, 501):
                    r = requests.get(url, headers=headers, timeout=6.0,
                                     stream=True)
                return (site, url, r.status_code in ok_codes)
            except Exception:
                return (site, url, False)

        with _cf.ThreadPoolExecutor(max_workers=8) as ex:
            return list(ex.map(lambda kv: _check(*kv), _SITES.items()))


get_registry().register(UsernameScanConnector())
