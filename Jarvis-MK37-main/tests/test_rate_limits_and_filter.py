"""
Tests pour :
  - agent.rate_limits : parsing headers, percent_used, remaining_label
  - ui._Api.get_router_status : skip des providers no_key + injection usage
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def reset_usage():
    from agent.rate_limits import reset
    reset()
    yield
    reset()


# ─────────────────────── rate_limits ───────────────────────

def test_anthropic_headers_parsed():
    from agent.rate_limits import record_from_headers, usage_summary
    record_from_headers("anthropic", {
        "anthropic-ratelimit-tokens-limit":     "100000",
        "anthropic-ratelimit-tokens-remaining": "40000",
    })
    s = usage_summary("anthropic")
    assert s is not None
    assert s["percent_used"] == 60   # 60% used = 40k restants sur 100k
    assert "40.0k" in s["remaining_label"]
    assert s["source"] == "tokens"


def test_openai_compat_headers_parsed():
    from agent.rate_limits import record_from_headers, usage_summary
    record_from_headers("groq", {
        "x-ratelimit-limit-tokens":     "30000",
        "x-ratelimit-remaining-tokens": "12000",
    })
    s = usage_summary("groq")
    assert s["percent_used"] == 60
    assert "12.0k" in s["remaining_label"]


def test_falls_back_to_requests_if_no_tokens():
    from agent.rate_limits import record_from_headers, usage_summary
    record_from_headers("openrouter", {
        "x-ratelimit-limit-requests":     "100",
        "x-ratelimit-remaining-requests": "25",
    })
    s = usage_summary("openrouter")
    assert s["percent_used"] == 75
    assert s["remaining_label"] == "25 req"
    assert s["source"] == "requests"


def test_no_useful_headers_returns_none():
    from agent.rate_limits import record_from_headers, usage_summary
    record_from_headers("foo", {"some-other-header": "x"})
    assert usage_summary("foo") is None


def test_record_never_raises_on_bad_headers():
    from agent.rate_limits import record_from_headers
    record_from_headers("x", None)
    record_from_headers("x", "not a dict")
    record_from_headers("x", {"x-ratelimit-limit-tokens": "not-a-number"})
    # Si on est arrivé ici sans exception, c'est OK


def test_short_num_formatting():
    from agent.rate_limits import _short_num
    assert _short_num(500) == "500"
    assert _short_num(2_500) == "2.5k"
    assert _short_num(1_234_567) == "1.2M"


# ─────────────────── get_router_status filter ───────────────────

def test_router_status_skips_providers_without_key(monkeypatch):
    """ui._Api.get_router_status doit ne PAS retourner les providers sans clé."""
    from ui import _Api, JarvisUI
    from agent.llm_router import get_router

    # Mock router avec config minimale : seulement groq + ollama (cf chain)
    class FakeUI: pass
    api = _Api.__new__(_Api)
    api._ui = FakeUI()

    router = get_router()
    monkeypatch.setattr(router, "cfg", {"groq_api_key": "xxx"})
    # Reset cooldown / last
    monkeypatch.setattr(router, "_cooldown", {})
    monkeypatch.setattr(router, "_last_provider", None)

    result = api.get_router_status()
    providers = [r["provider"] for r in result["providers"]]
    # Ollama toujours présent
    assert "ollama" in providers
    # Groq présent (clé fournie)
    assert "groq" in providers
    # Tous les autres absents (no key)
    for absent in ("anthropic", "openai", "gemini", "mistral", "cerebras",
                   "openrouter", "huggingface", "intelx"):
        assert absent not in providers, f"{absent} ne devrait PAS apparaître sans clé"


def test_router_status_includes_usage_after_call(monkeypatch):
    """Si rate_limits a des données pour un provider, get_router_status doit
    les inclure dans le payload."""
    from ui import _Api
    from agent.llm_router import get_router
    from agent.rate_limits import record_from_headers

    record_from_headers("groq", {
        "x-ratelimit-limit-tokens":     "30000",
        "x-ratelimit-remaining-tokens": "9000",
    })

    api = _Api.__new__(_Api)
    api._ui = object()
    router = get_router()
    monkeypatch.setattr(router, "cfg", {"groq_api_key": "xxx"})
    monkeypatch.setattr(router, "_cooldown", {})

    result = api.get_router_status()
    groq_row = next(r for r in result["providers"] if r["provider"] == "groq")
    assert groq_row["usage"] is not None
    assert groq_row["usage"]["percent_used"] == 70


def test_ollama_always_shown_as_unlimited(monkeypatch):
    from ui import _Api
    from agent.llm_router import get_router
    api = _Api.__new__(_Api)
    api._ui = object()
    router = get_router()
    monkeypatch.setattr(router, "cfg", {})  # aucune clé
    monkeypatch.setattr(router, "_cooldown", {})

    result = api.get_router_status()
    ollama_row = next(r for r in result["providers"] if r["provider"] == "ollama")
    assert ollama_row["usage"]["source"] == "local"
    assert "∞" in ollama_row["usage"]["remaining_label"]
