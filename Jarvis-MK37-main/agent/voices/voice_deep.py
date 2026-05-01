"""
Voie 2 — DEEP : Claude Sonnet supervise specialists pour réponses approfondies.

Pipeline :
  1. RAG inject (top 5 souvenirs pertinents)
  2. Superviseur (Claude/Gemini Pro) choisit specialist(s)
  3. Dispatch (parallèle si plusieurs)
  4. Self-critique (score 1-10)
  5. Si < 7 : relance ciblée, sinon synthèse
  6. Synthèse finale

Specialists accessibles : code, vision, research, reasoning, creative.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from agent.voices.base import Voice, VoiceResponse


SUPERVISOR_PROVIDERS = ["anthropic", "gemini", "deepseek", "openai"]
SUPERVISOR_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "gemini":    "gemini-2.5-pro",
    "deepseek":  "deepseek-chat",
    "openai":    "gpt-4o-mini",
}

# Specialists rattachés à Voie 2
DEEP_SPECIALISTS = ["code", "vision", "research", "reasoning", "creative"]

CRITIQUE_THRESHOLD = 7   # < 7 → relance avec correction
MAX_RETRIES = 1          # 1 relance max pour éviter boucles infinies


SUPERVISOR_SYSTEM = """Tu es le superviseur de la Voie 2 (DEEP) de Jarvis.
Tu reçois une requête. Pour répondre :

1. Choisis 1 à 3 specialists parmi : code, vision, research, reasoning, creative.
2. Pour chacun, formule une sous-question précise et adaptée à sa spécialité.
3. Réponds UNIQUEMENT en JSON :
{"specialists": [{"name": "research", "subquery": "...", "reason": "..."}], "synthesis_note": "ce que je veux dans la réponse finale"}

Si la requête est triviale, retourne {"specialists": [], "synthesis_note": "réponse directe"}."""

CRITIQUE_SYSTEM = """Évalue cette réponse de 1 à 10 selon :
- Pertinence à la question
- Profondeur d'analyse
- Précision factuelle

Réponds UNIQUEMENT en JSON : {"score": <int 1-10>, "issues": ["..."], "fix": "comment améliorer"}"""


class VoiceDeep(Voice):
    voice_id    = 2
    name        = "deep"
    description = "Supervise specialists pour réponses approfondies."

    def process(self, query: str, context: Optional[dict] = None) -> VoiceResponse:
        from agent.llm_router import get_router

        start = self._start_timer()
        router = get_router()

        # 1. RAG (placeholder — Phase 4 le branchera vraiment)
        memory_ctx = self._rag_inject(query, context)

        # 2. Plan : choisis les specialists
        plan = self._make_plan(query, memory_ctx, router)
        specs = plan.get("specialists", [])

        if not specs:
            # Pas de specialists → réponse directe via supervisor
            return self._direct_synthesis(query, memory_ctx, router, start)

        # 3. Dispatch specialists en parallèle
        results = self._run_specialists_parallel(specs, memory_ctx, router)

        # 4. Synthèse + critique
        synthesis = self._synthesize(query, results, plan.get("synthesis_note", ""), router)
        critique = self._critique(query, synthesis, router)

        # 5. Si score bas, relance
        retries = 0
        while critique.get("score", 10) < CRITIQUE_THRESHOLD and retries < MAX_RETRIES:
            self._log(f"⚠️ critique score {critique['score']}/10 — relance")
            fix_hint = critique.get("fix", "")
            synthesis = self._synthesize(
                query, results, plan.get("synthesis_note", "") + f"\n\nIMPROVE: {fix_hint}",
                router,
            )
            critique = self._critique(query, synthesis, router)
            retries += 1

        return self._build_response(
            text=synthesis,
            start=start,
            provider_used=router.last_provider or "deep",
            specialists_called=[s["name"] for s in specs],
            raw_outputs=[r["output"] for r in results],
            metadata={"critique": critique, "retries": retries, "plan": plan},
        )

    # ---------- pipeline steps ----------

    def _rag_inject(self, query: str, context: Optional[dict]) -> str:
        """Phase 4 branchera la vraie mémoire ici. Pour l'instant, passe-through."""
        if not context:
            return ""
        try:
            from memory.memory_manager import format_memory_for_prompt, load_memory
            return format_memory_for_prompt(load_memory())
        except Exception:
            return ""

    def _make_plan(self, query: str, memory_ctx: str, router) -> dict:
        prompt = f"Mémoire pertinente:\n{memory_ctx}\n\nRequête: {query}\n\nJSON:"
        for provider in SUPERVISOR_PROVIDERS:
            try:
                raw = router.generate(
                    prompt=prompt,
                    system=SUPERVISOR_SYSTEM,
                    model=SUPERVISOR_MODELS.get(provider),
                    temperature=0.3,
                    max_tokens=400,
                )
                return self._extract_json(raw) or {"specialists": [], "synthesis_note": ""}
            except Exception:
                continue
        return {"specialists": [], "synthesis_note": ""}

    def _run_specialists_parallel(self, specs: list[dict], memory_ctx: str, router) -> list[dict]:
        """Run specialists en parallèle via asyncio.to_thread."""
        async def _run_all():
            tasks = [
                asyncio.to_thread(self._call_specialist, s, memory_ctx, router)
                for s in specs
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        try:
            results = asyncio.run(_run_all())
        except RuntimeError:
            # Already in event loop : fallback séquentiel
            results = [self._call_specialist(s, memory_ctx, router) for s in specs]

        out = []
        for s, r in zip(specs, results):
            if isinstance(r, Exception):
                out.append({"name": s["name"], "output": f"[error] {r}"})
            else:
                out.append({"name": s["name"], "output": r})
        return out

    def _call_specialist(self, spec: dict, memory_ctx: str, router) -> str:
        """Appelle un specialist via le SPECIALISTS dict de agent_dispatcher."""
        from agent.agent_dispatcher import SPECIALISTS

        name = spec.get("name", "chat")
        subquery = spec.get("subquery", "")
        s = SPECIALISTS.get(name) or SPECIALISTS["chat"]

        system = f"Tu es un {s.name}. {s.description}"
        if memory_ctx:
            system += f"\n\nContexte mémoire:\n{memory_ctx[:1000]}"

        try:
            return router.generate(
                prompt=subquery,
                system=system,
                model=s.model,
                temperature=0.5,
                max_tokens=2048,
            )
        except Exception as e:
            return f"[{name} error] {e}"

    def _synthesize(self, query: str, results: list[dict], note: str, router) -> str:
        if not results:
            return ""
        results_str = "\n\n".join(
            f"### {r['name']}:\n{r['output']}" for r in results
        )
        prompt = (
            f"Requête utilisateur: {query}\n\n"
            f"Résultats des specialists:\n{results_str}\n\n"
            f"Consigne synthèse: {note}\n\n"
            f"Synthèse finale (réponse directe à l'utilisateur):"
        )
        for provider in SUPERVISOR_PROVIDERS:
            try:
                return router.generate(
                    prompt=prompt,
                    system="Synthétise ces sources en une réponse claire, sans répéter la structure.",
                    model=SUPERVISOR_MODELS.get(provider),
                    temperature=0.5,
                    max_tokens=2048,
                )
            except Exception:
                continue
        # Last resort : concat des outputs
        return "\n\n".join(r["output"] for r in results if r.get("output"))

    def _critique(self, query: str, answer: str, router) -> dict:
        prompt = f"Question: {query}\n\nRéponse:\n{answer}\n\nÉvaluation JSON:"
        try:
            raw = router.generate(
                prompt=prompt,
                system=CRITIQUE_SYSTEM,
                temperature=0.0,
                max_tokens=200,
            )
            data = self._extract_json(raw)
            if data:
                return data
        except Exception:
            pass
        return {"score": 7, "issues": [], "fix": ""}

    def _direct_synthesis(self, query, memory_ctx, router, start) -> VoiceResponse:
        """Pas de specialists → supervisor répond direct."""
        for provider in SUPERVISOR_PROVIDERS:
            try:
                text = router.generate(
                    prompt=f"Mémoire:\n{memory_ctx}\n\n{query}" if memory_ctx else query,
                    system="Tu es Jarvis. Réponds de manière approfondie mais concise.",
                    model=SUPERVISOR_MODELS.get(provider),
                    temperature=0.5,
                    max_tokens=2048,
                )
                return self._build_response(
                    text=text, start=start, provider_used=provider,
                )
            except Exception:
                continue
        return self._build_response(
            text="[VoiceDeep] tous les supervisors ont échoué",
            start=start, provider_used="error",
        )

    @staticmethod
    def _extract_json(raw: str) -> Optional[dict]:
        if not raw:
            return None
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
