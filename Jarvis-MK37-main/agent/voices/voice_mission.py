"""
Voie 3 — MISSION async : décompose les requêtes long-terme et schedule.

Joue le rôle de "project manager" :
  1. Reçoit la query
  2. Décompose en 1 ou plusieurs sub-missions (Claude/DeepSeek planner)
  3. Schedule les sub-missions dans MissionStore
  4. Retourne immédiatement avec l'ID de la mission top-level
  5. Le mission_runner (thread BG) exécute en async

Pour les missions, on préfère DeepSeek (10x moins cher que Claude pour qualité
similaire en raisonnement long).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Optional

from agent.mission_models import Mission
from agent.mission_store import MissionStore
from agent.voices.base import Voice, VoiceResponse


PLANNER_PROVIDERS = ["deepseek", "anthropic", "gemini", "openai"]
PLANNER_MODELS = {
    "deepseek":  "deepseek-chat",
    "anthropic": "claude-sonnet-4-6",
    "gemini":    "gemini-2.5-pro",
    "openai":    "gpt-4o-mini",
}


PLANNER_SYSTEM = """Tu es le project manager des missions long-terme de Jarvis.

Pour la requête utilisateur, décompose en 1 à 5 sub-missions claires.
Chaque sub-mission doit être autonome, avec un objectif vérifiable.

Réponds en JSON strict :
{
  "summary": "ce que la mission va produire au final",
  "subtasks": [
    {"description": "...", "voice_target": 2, "specialists": ["research"]},
    {"description": "...", "voice_target": 4, "specialists": ["osint"]}
  ]
}

voice_target : 1 (fast factuel), 2 (deep recherche/code), 4 (uncensored/cybersec).
Si la requête est simple, mets une seule subtask."""


class VoiceMission(Voice):
    voice_id    = 3
    name        = "mission"
    description = "Décompose et schedule les missions long-terme."

    def __init__(self, store: Optional[MissionStore] = None):
        self.store = store or MissionStore()

    def process(self, query: str, context: Optional[dict] = None) -> VoiceResponse:
        start = self._start_timer()

        # 1. Plan
        plan = self._make_plan(query, context)

        # 2. Crée Mission top-level
        top_id = str(uuid.uuid4())
        top = Mission(
            id=top_id,
            description=query,
            voice_used=3,
            metadata={
                "summary": plan.get("summary", ""),
                "context": context or {},
                "is_top_level": True,
            },
        )

        # 3. Crée sub-missions (si plusieurs subtasks)
        subtasks = plan.get("subtasks", []) or [{"description": query, "voice_target": 2}]
        sub_ids = []
        for st in subtasks:
            sub_id = str(uuid.uuid4())
            sub = Mission(
                id=sub_id,
                description=st.get("description", query),
                parent_id=top_id,
                voice_used=int(st.get("voice_target", 2)),
                metadata={
                    "specialists": st.get("specialists", []),
                    "parent_query": query,
                },
            )
            self.store.add(sub)
            sub_ids.append(sub_id)

        top.subtask_ids = sub_ids
        self.store.add(top)

        n = len(sub_ids)
        text = (
            f"🎯 Mission #{top_id[:8]} planifiée ({n} sous-tâche{'s' if n > 1 else ''}). "
            f"Je traite ça en arrière-plan, je te notifie quand c'est prêt.\n\n"
            f"Résumé : {plan.get('summary', query)}"
        )
        return self._build_response(
            text=text,
            start=start,
            provider_used="mission_runner",
            metadata={
                "mission_id": top_id,
                "subtask_ids": sub_ids,
                "plan": plan,
            },
        )

    # ---------- planner ----------

    def _make_plan(self, query: str, context: Optional[dict]) -> dict:
        from agent.llm_router import get_router

        router = get_router()
        ctx_str = ""
        if context:
            ctx_str = f"\nContexte: {json.dumps(context, ensure_ascii=False)[:300]}"
        prompt = f"Requête: {query}{ctx_str}\n\nJSON plan:"

        for provider in PLANNER_PROVIDERS:
            try:
                raw = router.generate(
                    prompt=prompt,
                    system=PLANNER_SYSTEM,
                    model=PLANNER_MODELS.get(provider),
                    temperature=0.3,
                    max_tokens=800,
                )
                parsed = self._extract_json(raw)
                if parsed and parsed.get("subtasks"):
                    return parsed
            except Exception:
                continue

        # Fallback : 1 seule subtask Voie 2
        return {
            "summary": query,
            "subtasks": [{"description": query, "voice_target": 2, "specialists": []}],
        }

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
