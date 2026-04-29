"""
Verifier Agent — vérifie chaque tool call, indépendamment du Executor.

Pipeline :
  1. Post-condition codable (psutil, pathlib, pygetwindow) via post_conditions.py
  2. Si inconclusive → LLM judge (modèle léger, prompt critic court)
  3. Résultat : PASS / FAIL / UNSURE + raison + suggestion
  4. Log KG : chaque vérification = fact utilisable plus tard

Usage :
    v = get_verifier()
    verdict = v.verify(goal, tool, params, result)
    if verdict.status == "FAIL": ...
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Verdict:
    status: str          # PASS | FAIL | UNSURE
    confidence: float    # 0.0 - 1.0
    reason: str
    suggestion: str = ""
    source: str = ""     # "code" | "llm" | "mixed"


JUDGE_SYSTEM = (
    "You are a strict verification agent. Given (user goal, tool executed, "
    "parameters, result text), decide if the ACTION ACTUALLY ACCOMPLISHED the goal. "
    "Do NOT be charitable — reported success means nothing, only observable evidence. "
    "Output JSON ONLY: {\"status\":\"PASS|FAIL|UNSURE\",\"confidence\":0..1,"
    "\"reason\":\"short\",\"suggestion\":\"what to try if FAIL\"}"
)


class Verifier:
    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model

    # ---------- public ----------

    def verify(
        self,
        goal: str,
        tool: str,
        params: dict,
        result: str,
    ) -> Verdict:
        # Step 1 : code-based post-condition
        from agent.post_conditions import check as code_check
        ok, reason = code_check(tool, params, result)

        if ok is True:
            v = Verdict("PASS", 0.95, reason, source="code")
            self._log(goal, tool, params, result, v)
            return v
        if ok is False:
            v = Verdict("FAIL", 0.95, reason,
                        suggestion=f"retry with alternative for {tool}",
                        source="code")
            self._log(goal, tool, params, result, v)
            return v

        # Step 2 : LLM-judge (fallback)
        v = self._llm_judge(goal, tool, params, result)
        v.source = "llm"
        self._log(goal, tool, params, result, v)
        return v

    # ---------- LLM judge ----------

    def _llm_judge(self, goal, tool, params, result) -> Verdict:
        try:
            from agent.llm_router import get_router
            prompt = (
                f"GOAL: {goal}\n"
                f"TOOL: {tool}\n"
                f"PARAMS: {json.dumps(params, ensure_ascii=False)[:400]}\n"
                f"RESULT: {str(result)[:600]}\n"
                "Did the action achieve the goal? JSON only."
            )
            txt = get_router().generate(
                prompt=prompt,
                system=JUDGE_SYSTEM,
                model=self.model,
                temperature=0.0,
                max_tokens=300,
            )
            import re
            txt = re.sub(r"```(?:json)?", "", txt).strip().rstrip("`").strip()
            data = json.loads(txt)
            return Verdict(
                status=str(data.get("status", "UNSURE")).upper(),
                confidence=float(data.get("confidence", 0.5)),
                reason=str(data.get("reason", "")),
                suggestion=str(data.get("suggestion", "")),
            )
        except Exception as e:
            return Verdict("UNSURE", 0.3, f"llm judge error: {e}")

    # ---------- KG log ----------

    def _log(self, goal, tool, params, result, verdict: Verdict) -> None:
        try:
            from memory.knowledge_graph import get_kg
            pkey = hashlib.md5(
                json.dumps(params or {}, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()[:10]
            key = f"{tool}:{pkey}:{int(time.time())}"
            value = json.dumps({
                "goal":       goal[:160],
                "tool":       tool,
                "params":     params,
                "result":     str(result)[:300],
                "status":     verdict.status,
                "confidence": verdict.confidence,
                "reason":     verdict.reason,
                "suggestion": verdict.suggestion,
                "source":     verdict.source,
            }, ensure_ascii=False)
            get_kg().add_fact(
                entity_name="verifier_log",
                key=key,
                value=value,
                entity_type="log",
                source="verifier",
                confidence=verdict.confidence,
            )
        except Exception as e:
            print(f"[Verifier] ⚠️ KG log failed: {e}")


_VERIFIER_SINGLETON: Optional[Verifier] = None


def get_verifier() -> Verifier:
    global _VERIFIER_SINGLETON
    if _VERIFIER_SINGLETON is None:
        _VERIFIER_SINGLETON = Verifier()
    return _VERIFIER_SINGLETON


def recall_lessons(tool: str, limit: int = 5) -> list[dict]:
    """Return past verdicts for a tool (used by planner pre-flight)."""
    try:
        from memory.knowledge_graph import get_kg
        rows = get_kg().search(f"\"tool\": \"{tool}\"", limit=limit * 3)
        out = []
        for r in rows:
            try:
                parsed = json.loads(r.get("value", "{}"))
                out.append(parsed)
            except Exception:
                continue
        return out[:limit]
    except Exception:
        return []
