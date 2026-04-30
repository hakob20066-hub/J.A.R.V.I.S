---
title: LLM Router — multi-provider, fallback auto
date: 2026-04-29
tags: [architecture, llm, router, mk37]
priority: high
---

# LLM Router

> Routage multi-provider hiérarchique avec fallback automatique sur quota/rate-limit.
> Fichier : `agent/llm_router.py`
> Liens : [[Architecture/Agent-Dispatcher]] | [[Operations/Setup-Env]]

---

## Hiérarchie par défaut

| Rang | Provider | Modèle par défaut | Force |
|------|----------|-------------------|-------|
| 1 | **anthropic** | `claude-sonnet-4-6` | Top qualité (code, raisonnement) |
| 2 | **openai** | `gpt-4o-mini` | Top qualité fallback |
| 3 | **gemini** | `gemini-2.5-flash` | Free tier généreux, multimodal |
| 4 | **deepseek** | `deepseek-chat` | Solide, prix imbattable |
| 5 | **openrouter** | `deepseek/deepseek-chat-v3-0324:free` | Gateway 300+ modèles |
| 6 | **groq** | `llama-3.3-70b-versatile` | Vitesse extrême (LPU) |
| 7 | **ollama** | `llama3.1` | 100 % offline, illimité (dernier recours) |

---

## Fallback automatique

Détection des erreurs `429`, `quota`, `rate limit`, `exhausted` → provider mis en **cooldown 60 s** et bascule au suivant. **Aucune intervention manuelle**.

```
Request → anthropic → 429 → cooldown 60s → openai → OK
                                                ↑
                                        retourne immédiatement
```

---

## Configuration

`config/api_keys.json` :

```json
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
```

Override possible via `.env` (cf [[Operations/Setup-Env]]).

---

## API publique

```python
from agent.llm_router import get_router

router = get_router()
text = router.complete(
    prompt="…",
    system="…",            # optional
    model_override=None,   # forcer un provider précis
    temperature=0.7,
)
```

Le router itère sur `default_chain`, saute les providers en cooldown, retourne dès la première réponse valide.

---

## Liens

- [[Architecture/Agent-Dispatcher]]
- [[Architecture/Stack-Technique]]
- [[Operations/Setup-Env]]
