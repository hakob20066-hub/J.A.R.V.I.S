"""
Suivi des quotas tokens/requests par provider via les headers de rate-limit
retournés par chaque API. Mise à jour à chaque appel (best-effort, jamais
bloquant). Lu par l'UI pour afficher "X% used".

Headers normalisés :
  - Anthropic : anthropic-ratelimit-tokens-{limit,remaining}
                anthropic-ratelimit-requests-{limit,remaining}
  - OpenAI / Groq / Mistral / OpenRouter / Cerebras / DeepSeek / Venice / Kindo / HackerGPT :
                x-ratelimit-limit-tokens, x-ratelimit-remaining-tokens
                x-ratelimit-limit-requests, x-ratelimit-remaining-requests
  - Gemini / HuggingFace / IntelX : pas de header standard → on ne tracke pas
  - Ollama : illimité local
"""
from __future__ import annotations

import threading
import time
from typing import Optional


_LOCK: threading.RLock = threading.RLock()
_USAGE: dict[str, dict] = {}


def _now() -> float:
    return time.time()


def _safe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except Exception:
        return None


def record_from_headers(provider: str, headers) -> None:
    """
    Met à jour _USAGE[provider] depuis les headers d'une réponse HTTP.
    `headers` peut être : dict, httpx.Headers, requests.structures.CaseInsensitive,
    ou tout objet supportant .get() ou itérable de paires.
    """
    if not headers:
        return
    try:
        # Normalise vers dict lower-case
        if hasattr(headers, "items"):
            h = {str(k).lower(): v for k, v in headers.items()}
        else:
            h = dict(headers)
        update: dict = {"updated_at": _now()}

        # Anthropic
        if provider == "anthropic":
            t_lim = _safe_int(h.get("anthropic-ratelimit-tokens-limit"))
            t_rem = _safe_int(h.get("anthropic-ratelimit-tokens-remaining"))
            r_lim = _safe_int(h.get("anthropic-ratelimit-requests-limit"))
            r_rem = _safe_int(h.get("anthropic-ratelimit-requests-remaining"))
        else:
            # OpenAI-compat
            t_lim = _safe_int(h.get("x-ratelimit-limit-tokens"))
            t_rem = _safe_int(h.get("x-ratelimit-remaining-tokens"))
            r_lim = _safe_int(h.get("x-ratelimit-limit-requests"))
            r_rem = _safe_int(h.get("x-ratelimit-remaining-requests"))

        # Au moins un signal utile sinon on ignore
        if t_lim is None and t_rem is None and r_lim is None and r_rem is None:
            return

        if t_lim is not None: update["tokens_limit"] = t_lim
        if t_rem is not None: update["tokens_remaining"] = t_rem
        if r_lim is not None: update["requests_limit"] = r_lim
        if r_rem is not None: update["requests_remaining"] = r_rem

        with _LOCK:
            cur = _USAGE.setdefault(provider, {})
            cur.update(update)
    except Exception:
        # Pas critique — on n'interrompt jamais l'appel LLM
        pass


def get_usage(provider: str) -> dict:
    with _LOCK:
        return dict(_USAGE.get(provider, {}))


def get_all_usage() -> dict[str, dict]:
    with _LOCK:
        return {k: dict(v) for k, v in _USAGE.items()}


def usage_summary(provider: str) -> Optional[dict]:
    """
    Retourne un résumé prêt-pour-UI :
      {percent_used, remaining_label, source: "tokens"|"requests"}
    None si pas de données pour ce provider.
    """
    u = get_usage(provider)
    if not u:
        return None
    # Préfère tokens (plus parlant que requests pour l'user)
    t_lim = u.get("tokens_limit")
    t_rem = u.get("tokens_remaining")
    if t_lim and t_rem is not None and t_lim > 0:
        used = t_lim - t_rem
        pct = max(0, min(100, int(round(100 * used / t_lim))))
        return {
            "percent_used":    pct,
            "remaining_label": _short_num(t_rem) + " tokens",
            "source":          "tokens",
        }
    r_lim = u.get("requests_limit")
    r_rem = u.get("requests_remaining")
    if r_lim and r_rem is not None and r_lim > 0:
        used = r_lim - r_rem
        pct = max(0, min(100, int(round(100 * used / r_lim))))
        return {
            "percent_used":    pct,
            "remaining_label": f"{r_rem} req",
            "source":          "requests",
        }
    return None


def _short_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def reset() -> None:
    """Pour les tests."""
    with _LOCK:
        _USAGE.clear()
