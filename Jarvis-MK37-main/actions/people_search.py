"""
people_search — pipeline OSINT nom+prénom → profils + emails + leaks.

Pipeline :
  1. Normalise (ascii, slugs, usernames candidats)
  2. Google dorks parallèles (linkedin, facebook, instagram, twitter/x,
     github, tiktok, youtube, pages blanches)
  3. Scan username multi-sites (sherlock-lite, HTTP HEAD)
  4. Génère emails permutés (prenom.nom@gmail/outlook/yahoo/hotmail/proton)
  5. Vérifie Gravatar (MD5 email)
  6. Chaîne IntelX sur chaque email trouvé via smart_dispatch osint
  7. Retourne rapport synthétique

Aucune clé API requise (DuckDuckGo + HEAD publics).
IntelX utilisé si clé présente.
"""
from __future__ import annotations

import concurrent.futures as _cf
import hashlib
import itertools
import re
import unicodedata
from datetime import datetime
from typing import Any, Callable, Optional

try:
    import requests
except Exception:
    requests = None  # fallback dégradé


# ─── Config ─────────────────────────────────────────────────────────────
USERNAME_SITES = {
    "GitHub":    "https://github.com/{u}",
    "Twitter/X": "https://x.com/{u}",
    "Instagram": "https://www.instagram.com/{u}/",
    "TikTok":    "https://www.tiktok.com/@{u}",
    "Reddit":    "https://www.reddit.com/user/{u}",
    "Twitch":    "https://www.twitch.tv/{u}",
    "YouTube":   "https://www.youtube.com/@{u}",
    "Pinterest": "https://www.pinterest.com/{u}/",
    "Steam":     "https://steamcommunity.com/id/{u}",
    "Gravatar":  "https://en.gravatar.com/{u}",
    "Keybase":   "https://keybase.io/{u}",
    "Medium":    "https://medium.com/@{u}",
    "Dev.to":    "https://dev.to/{u}",
    "GitLab":    "https://gitlab.com/{u}",
}

SOCIAL_DORKS = {
    "LinkedIn":     'site:linkedin.com/in "{q}"',
    "Facebook":     'site:facebook.com "{q}"',
    "Instagram":    'site:instagram.com "{q}"',
    "Twitter/X":    '(site:twitter.com OR site:x.com) "{q}"',
    "GitHub":       'site:github.com "{q}"',
    "TikTok":       'site:tiktok.com "{q}"',
    "YouTube":      'site:youtube.com "{q}"',
    "PagesJaunes":  'site:pagesjaunes.fr "{q}"',
    "Viadeo":       'site:viadeo.com "{q}"',
    "Xing":         'site:xing.com "{q}"',
    "ResearchGate": 'site:researchgate.net "{q}"',
    "Medium":       'site:medium.com "{q}"',
}

EMAIL_DOMAINS = [
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "yahoo.fr", "proton.me", "protonmail.com", "icloud.com",
    "live.fr", "orange.fr", "free.fr", "laposte.net", "wanadoo.fr",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (OSINT-Scan)"}
HEAD_TIMEOUT = 4.0


# ─── Helpers ────────────────────────────────────────────────────────────
def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _slug(s: str) -> str:
    s = _ascii(s).lower()
    return re.sub(r"[^a-z0-9]", "", s)


def _split_name(full: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"\s+", full.strip()) if p]
    if len(parts) < 2:
        return (parts[0], "") if parts else ("", "")
    return parts[0], " ".join(parts[1:])


def _usernames(first: str, last: str) -> list[str]:
    f, l = _slug(first), _slug(last)
    if not f and not l:
        return []
    cands = {
        f + l, l + f, f + "." + l, f + "_" + l, f[:1] + l, f + l[:1],
        f, l,
    }
    cands |= {c + str(n) for c in list(cands) for n in (1, 7, 23, 99)}
    return sorted(c for c in cands if c and len(c) >= 3)


def _emails(first: str, last: str, years: list[int] | None = None) -> list[str]:
    f, l = _slug(first), _slug(last)
    if not f or not l:
        return []
    locals_ = {f + "." + l, f + l, f[:1] + l, f + "." + l[:1], l + "." + f}
    # variantes avec année de naissance (95, 1995, 23, etc.)
    if years:
        y_short = {str(y)[-2:] for y in years}
        y_full  = {str(y)    for y in years}
        for y in (y_short | y_full):
            locals_ |= {f + l + y, f + "." + l + y, f + y + l, f[:1] + l + y}
    out = []
    for lp in locals_:
        for d in EMAIL_DOMAINS:
            out.append(f"{lp}@{d}")
    return out


def _resolve_years(age: Any, year: Any) -> list[int]:
    """Retourne liste d'années de naissance candidates."""
    now = datetime.now().year
    ys: set[int] = set()
    # année explicite
    if year:
        try:
            y = int(str(year).strip()[:4])
            if 1900 < y <= now:
                ys.add(y)
        except Exception:
            pass
    # âge précis -> 2 années (anniv passé ou non)
    if age is not None:
        try:
            a = int(age)
            if 0 < a < 120:
                ys.add(now - a)
                ys.add(now - a - 1)
        except Exception:
            pass
    return sorted(ys)


def _gravatar_url(email: str) -> str:
    h = hashlib.md5(email.strip().lower().encode()).hexdigest()
    return f"https://www.gravatar.com/avatar/{h}?d=404"


def _head_ok(url: str) -> bool:
    if not requests:
        return False
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True,
                          timeout=HEAD_TIMEOUT)
        if r.status_code == 200:
            return True
        if r.status_code in (403, 405):
            # certains sites bloquent HEAD, tente GET minimal
            r = requests.get(url, headers=HEADERS, timeout=HEAD_TIMEOUT,
                             stream=True)
            return r.status_code == 200
        return False
    except Exception:
        return False


def _ddg(query: str, n: int = 5) -> list[dict]:
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
    except Exception as e:
        return [{"title": "", "snippet": f"ddg error: {e}", "url": ""}]


# ─── Pipeline steps ─────────────────────────────────────────────────────
def _scan_usernames(usernames: list[str]) -> dict[str, list[str]]:
    """Retourne {username: [sites trouvés]}."""
    jobs = [(u, site, tpl.format(u=u))
            for u in usernames
            for site, tpl in USERNAME_SITES.items()]
    hits: dict[str, list[str]] = {}
    with _cf.ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(_head_ok, url): (u, site)
                for u, site, url in jobs}
        for fut in _cf.as_completed(futs):
            u, site = futs[fut]
            try:
                if fut.result():
                    hits.setdefault(u, []).append(site)
            except Exception:
                pass
    return hits


def _check_gravatars(emails: list[str]) -> list[str]:
    with _cf.ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(lambda e: (e, _head_ok(_gravatar_url(e))),
                              emails))
    return [e for e, ok in results if ok]


def _google_dorks(full_name: str, extras: list[str] | None = None) -> dict[str, list[dict]]:
    """extras : termes supplémentaires joints au dork (ville, adresse, année...)."""
    suffix = "".join(f' "{x}"' for x in (extras or []) if x)
    out: dict[str, list[dict]] = {}
    with _cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_ddg, tpl.format(q=full_name) + suffix, 3): site
                for site, tpl in SOCIAL_DORKS.items()}
        for fut in _cf.as_completed(futs):
            site = futs[fut]
            try:
                res = fut.result()
                res = [r for r in res if r.get("url")]
                if res:
                    out[site] = res
            except Exception:
                pass
    return out


def _intelx_on_emails(emails: list[str], speak=None) -> dict[str, str]:
    """Pour chaque email plausible, interroge IntelX via smart_dispatch."""
    try:
        from agent.agent_dispatcher import dispatch
    except Exception as e:
        return {"_error": f"dispatch unavailable: {e}"}
    out: dict[str, str] = {}
    for em in emails[:5]:  # cap pour coût
        try:
            r = dispatch(f"osint leak {em}", speak=None)
            res = "\n".join(str(x) for x in r.get("results", []))[:400]
            if res.strip():
                out[em] = res
        except Exception as e:
            out[em] = f"error: {e}"
    return out


# ─── Entry point ────────────────────────────────────────────────────────
def people_search(
    parameters: Optional[dict] = None,
    player: Any = None,
    speak: Optional[Callable[[str], None]] = None,
) -> str:
    """
    parameters: {
      "name":          "Jean Dupont",   # obligatoire
      "city":          "Paris",         # optionnel → affine dorks
      "address":       "12 rue X",      # optionnel → dork reverse adresse
      "age":           29,              # optionnel → estime année naissance
      "birth_year":    1995,            # optionnel → année précise
      "deep":          True,            # False = pas d'IntelX
      "max_usernames": 12,              # cap scan username
    }
    """
    p = parameters or {}
    full    = (p.get("name") or p.get("query") or "").strip()
    city    = (p.get("city") or "").strip()
    address = (p.get("address") or "").strip()
    age     = p.get("age")
    byear   = p.get("birth_year") or p.get("year")
    deep    = bool(p.get("deep", True))
    cap     = int(p.get("max_usernames", 12))

    if not full or len(full.split()) < 2:
        return "people_search: fournir nom ET prénom (ex: 'Jean Dupont')."

    first, last = _split_name(full)
    years = _resolve_years(age, byear)

    # NB: pas de speak() pré-scan — anti multi-réponse, le turn parle UNE seule fois après tool.

    extras = [city, address] + [str(y) for y in years]
    usernames = _usernames(first, last)[:cap]
    emails    = _emails(first, last, years)

    # parallèle : dorks + username scan + gravatar
    with _cf.ThreadPoolExecutor(max_workers=3) as ex:
        f_dorks = ex.submit(_google_dorks, full, extras)
        f_users = ex.submit(_scan_usernames, usernames)
        f_grav  = ex.submit(_check_gravatars, emails)
        dorks  = f_dorks.result()
        hits   = f_users.result()
        grav   = f_grav.result()

    intelx = _intelx_on_emails(grav or emails[:5], speak=speak) if deep else {}

    # ── Rapport ──
    header_bits = [full]
    if city:    header_bits.append(city)
    if address: header_bits.append(address)
    if years:   header_bits.append(f"né {years[0]}" + (f"/{years[1]}" if len(years) > 1 else ""))
    lines = [f"=== PEOPLE SEARCH — {' / '.join(header_bits)} ===\n"]

    if dorks:
        lines.append("-- Profils publics (dorks) --")
        for site, res in dorks.items():
            for r in res[:2]:
                lines.append(f"  [{site}] {r['title'][:70]} — {r['url']}")
        lines.append("")

    if hits:
        lines.append("-- Username collisions (comptes existants) --")
        for u, sites in sorted(hits.items(), key=lambda x: -len(x[1])):
            lines.append(f"  {u} → {', '.join(sites)}")
        lines.append("")

    if grav:
        lines.append("-- Gravatar HIT (email confirmé) --")
        for e in grav:
            lines.append(f"  ✓ {e}")
        lines.append("")

    if intelx:
        lines.append("-- Leaks IntelX --")
        for e, r in intelx.items():
            lines.append(f"  [{e}]")
            lines.append(f"    {r[:200]}")
        lines.append("")

    if not (dorks or hits or grav or intelx):
        lines.append("Rien trouvé. Essaye avec ville ou métier.")

    out = "\n".join(lines)
    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"PeopleSearch: {len(hits)} users, "
                             f"{len(grav)} grav, {len(intelx)} leaks")
        except Exception:
            pass
    return out


if __name__ == "__main__":
    import sys
    name = " ".join(sys.argv[1:]) or "Jean Dupont"
    print(people_search({"name": name, "deep": False}))
