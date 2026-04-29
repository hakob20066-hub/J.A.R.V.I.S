"""
Specialists — 9 rôles spécialisés invocables via le tool `delegate_task`.

Chaque spécialiste = (system_prompt, preferred_model).
Le routage passe par LLMRouter donc fallback multi-provider gratuit.
"""

from __future__ import annotations

from typing import Optional


SPECIALISTS: dict[str, dict] = {
    "coder": {
        "model": "claude-sonnet-4-6",
        "system": (
            "You are a senior software engineer. Output clean, production-ready code. "
            "No commentary unless asked. Prefer minimal diffs. Always match the target language. "
            "If the user context implies tests, include them. Never invent APIs."
        ),
    },
    "researcher": {
        "model": "gemini-2.5-flash",
        "system": (
            "You are a meticulous research analyst. Gather facts, cite sources, "
            "and write a structured brief (TL;DR, key points, sources). "
            "Flag uncertainty. No filler."
        ),
    },
    "writer": {
        "model": "claude-sonnet-4-6",
        "system": (
            "You are a professional writer. Adapt tone to the requested register. "
            "Tight paragraphs, strong verbs, no filler. Deliver the draft only."
        ),
    },
    "planner": {
        "model": "gemini-2.5-flash-lite",
        "system": (
            "You are a tactical planner. Break the goal into ≤50 actionable steps with "
            "owner, dependencies, and success criteria. Output JSON only."
        ),
    },
    "debugger": {
        "model": "claude-sonnet-4-6",
        "system": (
            "You are a debugging expert. Given an error and context, identify root cause, "
            "propose a minimal fix, and explain why. Output: {cause, fix, patch}."
        ),
    },
    "analyst": {
        "model": "gemini-2.5-flash",
        "system": (
            "You are a data analyst. Given raw data, extract insights, trends, anomalies. "
            "Output: bullet insights + suggested next actions. Be quantitative."
        ),
    },
    "translator": {
        "model": "gemini-2.5-flash",
        "system": (
            "You are a professional translator. Translate faithfully preserving tone, "
            "register, names, numbers. Output ONLY the translation."
        ),
    },
    "summarizer": {
        "model": "gemini-2.5-flash-lite",
        "system": (
            "You compress text aggressively without losing critical info. "
            "Output: 3-5 bullets + 1-line TL;DR."
        ),
    },
    "critic": {
        "model": "claude-sonnet-4-6",
        "system": (
            "You are a ruthless but fair critic. Identify weaknesses, logical gaps, "
            "missed angles. Output: top-3 issues + top-3 improvements. No flattery."
        ),
    },
}


def list_specialists() -> list[str]:
    return list(SPECIALISTS.keys())


def delegate(role: str, task: str, context: str = "") -> str:
    """
    Dispatch un sous-tâche à un spécialiste. Utilise le LLMRouter pour fallback.
    Retourne la sortie texte (ou erreur formatée).
    """
    from agent.llm_router import get_router

    spec = SPECIALISTS.get(role)
    if not spec:
        return f"[Specialists] ❌ Unknown role: {role}. Available: {', '.join(list_specialists())}"

    prompt = f"TASK:\n{task}"
    if context:
        prompt += f"\n\nCONTEXT:\n{context}"

    try:
        out = get_router().generate(
            prompt=prompt,
            system=spec["system"],
            model=spec["model"],
            temperature=0.5,
            max_tokens=4096,
        )
        return out
    except Exception as e:
        return f"[Specialists/{role}] ⚠️ failed: {e}"
