"""
Voie 1 — FAST : réponse directe ultra-rapide, sans specialists.

Provider primaire : Groq Llama-3.3-70B (~500 tok/s, < 2s end-to-end).
Fallback chain : Cerebras → Mistral → OpenRouter.

Pas de RAG, pas de critique, pas d'orchestration. Vise les questions courtes
factuelles ou les réponses chat informelles.
"""

from __future__ import annotations

from typing import Optional

from agent.voices.base import Voice, VoiceResponse


FAST_PROVIDERS = ["groq", "cerebras", "mistral", "openrouter"]
FAST_MODELS = {
    "groq":       "llama-3.3-70b-versatile",
    "cerebras":   "llama-3.3-70b",
    "mistral":    "mistral-large-latest",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
}


class VoiceFast(Voice):
    voice_id    = 1
    name        = "fast"
    description = "Réponse directe rapide, pas de specialists."

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt or (
            "Tu es Jarvis. Réponds de manière concise et directe. "
            "Pas de blabla, pas de disclaimers. Va à l'essentiel."
        )

    def process(self, query: str, context: Optional[dict] = None) -> VoiceResponse:
        from agent.llm_router import get_router

        start = self._start_timer()
        router = get_router()

        # Itère sur les providers FAST en priorité ; le router gère le fallback global
        last_err: Optional[Exception] = None
        for provider in FAST_PROVIDERS:
            try:
                model = FAST_MODELS.get(provider)
                text = router.generate(
                    prompt=query,
                    system=self.system_prompt,
                    model=model,
                    temperature=0.5,
                    max_tokens=1024,
                )
                if text:
                    self._log(f"✅ {provider}/{model}")
                    return self._build_response(
                        text=text,
                        start=start,
                        provider_used=provider,
                    )
            except Exception as e:
                last_err = e
                continue

        # Tous les FAST providers ont échoué : laisse le router choisir n'importe quoi
        try:
            text = router.generate(
                prompt=query,
                system=self.system_prompt,
                temperature=0.5,
                max_tokens=1024,
            )
            return self._build_response(
                text=text,
                start=start,
                provider_used=router.last_provider or "fallback",
            )
        except Exception as e:
            return self._build_response(
                text=f"[VoiceFast error] {e or last_err}",
                start=start,
                provider_used="error",
                metadata={"error": str(e)},
            )
