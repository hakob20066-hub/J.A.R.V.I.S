"""
LLM Router — multi-provider, hiérarchie par puissance, fallback auto sur quota/rate limit.

Hiérarchie par défaut (plus puissant → plus faible) :
  1. anthropic  (Claude Opus/Sonnet)        — top qualité
  2. openai     (GPT-4o / o-series)         — top qualité
  3. gemini     (Gemini 2.5 pro/flash)      — fort + quota free
  4. deepseek   (DeepSeek V3 / Coder)       — solide, pas cher
  5. openrouter (modèles variés free)       — fallback gratuit
  6. groq       (Llama 3.3 70B)             — rapide free
  7. ollama     (local, illimité offline)   — dernier recours

Détection auto quota / rate limit / 429 / "exhausted" → provider mis en cooldown
(par défaut 60s) et passage au suivant. Aucune intervention manuelle.

Config : config/api_keys.json
{
  "anthropic_api_key":  "sk-ant-...",
  "openai_api_key":     "sk-...",
  "gemini_api_key":     "...",
  "deepseek_api_key":   "...",
  "openrouter_api_key": "sk-or-...",
  "groq_api_key":       "...",
  "ollama_base_url":    "http://localhost:11434",
  "router": {
    "default_chain": ["anthropic","openai","gemini","deepseek","openrouter","groq","ollama"],
    "model_map": {
      "anthropic":  "claude-sonnet-4-6",
      "openai":     "gpt-4o-mini",
      "gemini":     "gemini-2.5-flash",
      "deepseek":   "deepseek-chat",
      "openrouter": "deepseek/deepseek-chat-v3-0324:free",
      "groq":       "llama-3.3-70b-versatile",
      "ollama":     "llama3.1"
    },
    "cooldown_seconds": 60
  }
}
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Hiérarchie providers GRATUITS uniquement (plus fort → plus faible)
DEFAULT_CHAIN = [
    "groq",        # Llama 3.3 70B — 14 400 req/jour free
    "cerebras",    # Llama 3.3 70B — inference ultra rapide free
    "mistral",     # Mistral Large — free tier La Plateforme
    "openrouter",  # modèles :free
    "gemini",      # 50 req/jour free
    "huggingface", # Inference API free
    "intelx",      # OSINT API : leaks, dark web, pastes, docs — free tier
    "ollama",      # local offline illimité
]

DEFAULT_MODELS = {
    "groq":        "llama-3.3-70b-versatile",
    "cerebras":    "llama-3.3-70b",
    "mistral":     "mistral-large-latest",
    "openrouter":  "meta-llama/llama-3.3-70b-instruct:free",
    "gemini":      "gemini-2.5-flash",
    "huggingface": "meta-llama/Llama-3.3-70B-Instruct",
    "intelx":      "intelligence-x-search",
    "ollama":      "llama3.1",
}

DEFAULT_COOLDOWN = 60  # secondes
PROVIDER_KEY_MAP = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "deepseek": "deepseek_api_key",
    "openrouter": "openrouter_api_key",
    "groq": "groq_api_key",
    "venice": "venice_api_key",
    "kindo": "kindo_api_key",
    "hackergpt": "hackergpt_api_key",
    "cerebras": "cerebras_api_key",
    "mistral": "mistral_api_key",
    "huggingface": "huggingface_api_key",
    "intelx": "intelx_api_key",
}


def _load_config() -> dict:
    if not API_CONFIG_PATH.exists():
        return {}
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _is_quota_error(exc: Exception) -> bool:
    """Détecte erreurs de quota / rate-limit pour déclencher cooldown."""
    msg = str(exc).lower()
    signals = [
        "429", "quota", "rate limit", "rate_limit", "ratelimit",
        "exhausted", "resource_exhausted", "too many requests",
        "insufficient_quota", "billing", "credit",
        "exceeded your current quota",
    ]
    return any(s in msg for s in signals)


class LLMRouter:
    """
    Usage :
        r = get_router()
        txt = r.generate(prompt="...", system="...")
        # => essaie chain dans l'ordre, skip providers en cooldown ou sans clé,
        #    bascule auto sur erreurs 429/quota
    """

    def __init__(self, chain: Optional[list[str]] = None):
        cfg             = _load_config()
        router_cfg      = cfg.get("router", {})
        self.cfg        = cfg
        self.chain      = chain or router_cfg.get("default_chain", DEFAULT_CHAIN)
        self.models     = {**DEFAULT_MODELS, **router_cfg.get("model_map", {})}
        self.cooldown_s = int(router_cfg.get("cooldown_seconds", DEFAULT_COOLDOWN))
        # provider -> timestamp expiration cooldown
        self._cooldown: dict[str, float] = {}
        self._last_provider: Optional[str] = None

    # ---------- public ----------

    def generate(
        self,
        prompt: str,
        system: str = "",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        # Override explicite : force un provider
        if model:
            provider = self._provider_from_model(model)
            if provider and self._usable(provider):
                try:
                    out = self._dispatch(provider, prompt, system, model, temperature, max_tokens)
                    self._last_provider = provider
                    return out
                except Exception as e:
                    self._handle_error(provider, e)

        # Chain fallback
        last_err: Optional[Exception] = None
        for provider in self.chain:
            if not self._usable(provider):
                continue
            try:
                m = self.models.get(provider)
                out = self._dispatch(provider, prompt, system, m, temperature, max_tokens)
                self._last_provider = provider
                print(f"[LLMRouter] ✅ {provider} ({m})")
                return out
            except Exception as e:
                last_err = e
                self._handle_error(provider, e)
                continue

        raise RuntimeError(f"All providers failed or in cooldown. Last error: {last_err}")

    def complete(self, prompt: str, system: str = "", **kw) -> str:
        return self.generate(prompt=prompt, system=system, **kw)

    @property
    def last_provider(self) -> Optional[str]:
        return self._last_provider

    def status(self) -> dict:
        now = time.time()
        return {
            "chain":    self.chain,
            "models":   self.models,
            "cooldown": {p: max(0, int(t - now)) for p, t in self._cooldown.items() if t > now},
            "last":     self._last_provider,
        }

    def reset_cooldowns(self) -> None:
        self._cooldown.clear()

    # ---------- error handling ----------

    def _handle_error(self, provider: str, exc: Exception) -> None:
        if _is_quota_error(exc):
            self._cooldown[provider] = time.time() + self.cooldown_s
            print(f"[LLMRouter] ⛔ {provider} quota/rate-limit → cooldown {self.cooldown_s}s")
        else:
            print(f"[LLMRouter] ⚠️ {provider} erreur: {exc}")

    def _usable(self, provider: str) -> bool:
        if not self._provider_available(provider):
            return False
        exp = self._cooldown.get(provider, 0)
        return exp <= time.time()

    # ---------- dispatch ----------

    def _dispatch(self, provider, prompt, system, model, temperature, max_tokens) -> str:
        fn: dict[str, Callable] = {
            # providers gratuits
            "groq":        self._call_groq,
            "cerebras":    self._call_cerebras,
            "mistral":     self._call_mistral,
            "openrouter":  self._call_openrouter,
            "gemini":      self._call_gemini,
            "huggingface": self._call_huggingface,
            "intelx":      self._call_intelx,
            "ollama":      self._call_ollama,
            # payants (gardés dispo si clé)
            "anthropic":   self._call_anthropic,
            "openai":      self._call_openai,
            "deepseek":    self._call_deepseek,
            "venice":      self._call_venice,
            "kindo":       self._call_kindo,
            "hackergpt":   self._call_hackergpt,
        }
        if provider not in fn:
            raise ValueError(f"Unknown provider: {provider}")
        return fn[provider](prompt, system, model, temperature, max_tokens)

    # ---------- availability ----------

    def _provider_available(self, provider: str) -> bool:
        if provider == "ollama":
            return True  # best-effort local
        k = PROVIDER_KEY_MAP.get(provider)
        return bool(k and self.cfg.get(k))

    def _provider_from_model(self, model: str) -> Optional[str]:
        m = model.lower()
        if m.startswith("claude"):  return "anthropic"
        if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
            return "openai"
        if m.startswith("gemini"):  return "gemini"
        if m.startswith("deepseek"): return "deepseek"
        if "/" in m:                return "openrouter"
        if "llama" in m or "mixtral" in m or "qwen" in m:
            return "groq" if self._provider_available("groq") else "ollama"
        return None

    # ---------- providers ----------

    def _call_anthropic(self, prompt, system, model, temperature, max_tokens) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.cfg["anthropic_api_key"])
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        parts = []
        for block in msg.content:
            txt = getattr(block, "text", None)
            if txt:
                parts.append(txt)
        return "".join(parts).strip()

    def _call_openai(self, prompt, system, model, temperature, max_tokens) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.cfg["openai_api_key"])
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_gemini(self, prompt, system, model, temperature, max_tokens) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.cfg["gemini_api_key"])
        m = genai.GenerativeModel(model_name=model, system_instruction=system or None)
        resp = m.generate_content(
            prompt,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
        )
        return (resp.text or "").strip()

    def _call_deepseek(self, prompt, system, model, temperature, max_tokens) -> str:
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["deepseek_api_key"],
            base_url="https://api.deepseek.com/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_openrouter(self, prompt, system, model, temperature, max_tokens) -> str:
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["openrouter_api_key"],
            base_url="https://openrouter.ai/api/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_groq(self, prompt, system, model, temperature, max_tokens) -> str:
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["groq_api_key"],
            base_url="https://api.groq.com/openai/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_venice(self, prompt, system, model, temperature, max_tokens) -> str:
        """Venice AI — OpenAI-compat, uncensored. https://docs.venice.ai"""
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["venice_api_key"],
            base_url="https://api.venice.ai/api/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_kindo(self, prompt, system, model, temperature, max_tokens) -> str:
        """Kindo — héberge WhiteRabbitNeo (cybersec). OpenAI-compat.
        https://www.kindo.ai/developers"""
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["kindo_api_key"],
            base_url="https://llm.kindo.ai/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_hackergpt(self, prompt, system, model, temperature, max_tokens) -> str:
        """HackerGPT — cybersec assistant. OpenAI-compat.
        https://docs.hackergpt.co"""
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["hackergpt_api_key"],
            base_url="https://www.hackergpt.co/api/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_cerebras(self, prompt, system, model, temperature, max_tokens) -> str:
        """Cerebras — inference ultra rapide, free tier généreux.
        https://inference-docs.cerebras.ai"""
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["cerebras_api_key"],
            base_url="https://api.cerebras.ai/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_mistral(self, prompt, system, model, temperature, max_tokens) -> str:
        """Mistral La Plateforme — OpenAI-compat, free tier.
        https://docs.mistral.ai"""
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["mistral_api_key"],
            base_url="https://api.mistral.ai/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_huggingface(self, prompt, system, model, temperature, max_tokens) -> str:
        """Hugging Face Inference API — OpenAI-compat, free tier.
        https://huggingface.co/docs/inference-providers"""
        from openai import OpenAI
        client = OpenAI(
            api_key=self.cfg["huggingface_api_key"],
            base_url="https://router.huggingface.co/v1",
        )
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_intelx(self, prompt, system, model, temperature, max_tokens) -> str:
        """Intelligence X — API OSINT (leaks, dark web, pastes, docs).
        Free tier disponible. https://intelx.io/account?tab=developer

        NB : ce n'est PAS un LLM. Le prompt = terme OSINT (email, domain, IP,
        username, btc-addr, etc.). Retourne les résultats formatés en texte.
        """
        import requests
        key = self.cfg["intelx_api_key"]
        base = self.cfg.get("intelx_base_url", "https://free.intelx.io")
        headers = {"x-key": key, "User-Agent": "jarvis-router/1.0"}

        # 1) Lancer la recherche
        search_payload = {
            "term":        prompt.strip(),
            "buckets":     [],
            "lookuplevel": 0,
            "maxresults":  25,
            "timeout":     20,
            "datefrom":    "",
            "dateto":      "",
            "sort":        4,   # date desc
            "media":       0,
            "terminate":   [],
        }
        r = requests.post(f"{base}/intelligent/search",
                          json=search_payload, headers=headers, timeout=30)
        r.raise_for_status()
        search_id = r.json().get("id")
        if not search_id:
            return "IntelX: search id missing."

        # 2) Récupérer résultats
        import time
        for _ in range(10):
            rr = requests.get(
                f"{base}/intelligent/search/result",
                params={"id": search_id, "limit": 25},
                headers=headers, timeout=20,
            )
            rr.raise_for_status()
            data = rr.json()
            if data.get("status") in (0, 1):   # 0=success, 1=no more
                break
            time.sleep(1)

        records = data.get("records", []) or []
        if not records:
            return f"IntelX: aucun résultat pour '{prompt}'."

        lines = [f"IntelX — {len(records)} résultats pour '{prompt}':"]
        for i, rec in enumerate(records[:25], 1):
            name   = rec.get("name", "")
            bucket = rec.get("bucket", "")
            date   = rec.get("date", "")
            size   = rec.get("size", 0)
            sysid  = rec.get("systemid", "")
            lines.append(f"{i:2d}. [{bucket}] {name} ({size}B) {date} id={sysid}")
        return "\n".join(lines)

    def _call_ollama(self, prompt, system, model, temperature, max_tokens) -> str:
        """
        Délègue au LocalLLMProvider (Ollama OU AirLLM selon hardware).
        Le provider est choisi au boot par hardware_detect.py.

        Si `model` est passé explicitement (model_override), on respecte ce
        choix mais on garde le backend local détecté.
        """
        from agent.local_llm_provider import get_local_provider
        provider = get_local_provider()
        if model and model != provider.model:
            print(f"[LLMRouter] ℹ️ local model override: {provider.model} → {model}")
            provider.model = model
        return provider.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )


# singleton
_ROUTER_SINGLETON: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _ROUTER_SINGLETON
    if _ROUTER_SINGLETON is None:
        _ROUTER_SINGLETON = LLMRouter()
    return _ROUTER_SINGLETON


def validate_provider_key(provider: str, value: str) -> tuple[bool, str]:
    key_name = PROVIDER_KEY_MAP.get(provider)
    if not key_name:
        return False, f"Unknown provider: {provider}"
    token = (value or "").strip()
    if len(token) < 8 or token.startswith("YOUR_"):
        return False, f"Invalid placeholder for {provider}"
    return True, f"Key format accepted for {provider}"
