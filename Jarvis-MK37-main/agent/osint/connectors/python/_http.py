"""
Base HTTP partagée pour tous les connecteurs Python OSINT.

- Session httpx async singleton (+ sync wrapper)
- User-Agent rotation, headers neutres
- Retry exponentiel (3 essais) sur 429/503/réseau
- Semaphore global (16 requêtes parallèles max)
- Timeout configurable (défaut 10s)
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Optional

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

try:
    import requests as _requests
    _REQUESTS = True
except ImportError:
    _REQUESTS = False

# ── User-Agents ──────────────────────────────────────────────────────────────
_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "curl/8.7.1",
]

DEFAULT_TIMEOUT = 10.0
DEFAULT_RETRIES = 3
_GLOBAL_SEM: Optional[asyncio.Semaphore] = None


def _ua() -> str:
    return random.choice(_UAS)


def _base_headers(extra: Optional[dict] = None) -> dict:
    h = {"User-Agent": _ua(), "Accept": "application/json, */*;q=0.8"}
    if extra:
        h.update(extra)
    return h


def _sem() -> asyncio.Semaphore:
    global _GLOBAL_SEM
    if _GLOBAL_SEM is None:
        _GLOBAL_SEM = asyncio.Semaphore(16)
    return _GLOBAL_SEM


# ── Async GET ────────────────────────────────────────────────────────────────

async def async_get(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    json_only: bool = False,
) -> dict:
    """
    Retourne {"ok": bool, "status": int, "data": dict|str, "elapsed_ms": int}.
    Retry exponentiel sur 429/503 et erreurs réseau.
    """
    if not _HTTPX:
        return await asyncio.to_thread(_sync_get, url, params=params,
                                       headers=headers, timeout=timeout)

    h = _base_headers(headers)
    async with _sem():
        for attempt in range(retries):
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=timeout,
                                             follow_redirects=True) as client:
                    r = await client.get(url, params=params, headers=h)
                elapsed = int((time.monotonic() - t0) * 1000)
                if r.status_code == 429 and attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if r.status_code == 503 and attempt < retries - 1:
                    await asyncio.sleep(1 + attempt)
                    continue
                try:
                    data = r.json() if json_only else (
                        r.json() if "json" in r.headers.get("content-type", "") else r.text
                    )
                except Exception:
                    data = r.text
                return {"ok": r.is_success, "status": r.status_code,
                        "data": data, "elapsed_ms": elapsed}
            except Exception as e:
                if attempt == retries - 1:
                    return {"ok": False, "status": 0, "data": str(e), "elapsed_ms": 0}
                await asyncio.sleep(2 ** attempt)
    return {"ok": False, "status": 0, "data": "semaphore_error", "elapsed_ms": 0}


async def async_head(
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: float = 5.0,
) -> dict:
    h = _base_headers(headers)
    if not _HTTPX:
        return await asyncio.to_thread(_sync_head, url, headers=h, timeout=timeout)
    async with _sem():
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout,
                                         follow_redirects=True) as client:
                r = await client.head(url, headers=h)
            elapsed = int((time.monotonic() - t0) * 1000)
            return {"ok": r.is_success, "status": r.status_code, "elapsed_ms": elapsed}
        except Exception as e:
            return {"ok": False, "status": 0, "data": str(e), "elapsed_ms": 0}


# ── Sync fallbacks (requests) ────────────────────────────────────────────────

def _sync_get(url: str, *, params=None, headers=None,
              timeout: float = DEFAULT_TIMEOUT) -> dict:
    if not _REQUESTS:
        return {"ok": False, "status": 0, "data": "no http library", "elapsed_ms": 0}
    h = _base_headers(headers)
    t0 = time.monotonic()
    try:
        r = _requests.get(url, params=params, headers=h,
                          timeout=timeout, allow_redirects=True)
        elapsed = int((time.monotonic() - t0) * 1000)
        try:
            data = r.json() if "json" in r.headers.get("content-type", "") else r.text
        except Exception:
            data = r.text
        return {"ok": r.ok, "status": r.status_code, "data": data, "elapsed_ms": elapsed}
    except Exception as e:
        return {"ok": False, "status": 0, "data": str(e), "elapsed_ms": 0}


def _sync_head(url: str, *, headers=None, timeout: float = 5.0) -> dict:
    if not _REQUESTS:
        return {"ok": False, "status": 0, "elapsed_ms": 0}
    t0 = time.monotonic()
    try:
        r = _requests.head(url, headers=headers or _base_headers(),
                           timeout=timeout, allow_redirects=True)
        elapsed = int((time.monotonic() - t0) * 1000)
        return {"ok": r.ok, "status": r.status_code, "elapsed_ms": elapsed}
    except Exception as e:
        return {"ok": False, "status": 0, "data": str(e), "elapsed_ms": 0}


def sync_get(url: str, **kwargs) -> dict:
    return _sync_get(url, **kwargs)
