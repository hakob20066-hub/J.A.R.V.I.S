"""
Agent Dispatcher — cerveau orchestrateur multi-agents.

Pipeline :
  prompt ─▶ classify() ─▶ plan() ─▶ select_specialist() ─▶ execute()

1. `classify(prompt)`  → détermine le type de tâche (code, osint, research...)
2. `plan(prompt, type)` → plan étape-par-étape adapté au type
3. `select_specialist(type)` → choisit l'agent + modèle + provider
4. `execute(plan)` → exécute chaque étape via l'agent sélectionné

Types de tâche reconnus :
    - code          : code_helper (rapide, un fichier)
    - build_project : dev_agent   (projet multi-fichiers)
    - osint         : intelx      (leaks, dark web, pastes)
    - cybersec      : kindo/venice (pentest, uncensored)
    - research      : web_search + LLM
    - reasoning     : deepseek-r1 (raisonnement profond)
    - creative      : mistral     (créatif UE)
    - vision        : gemini      (image)
    - chat          : fallback router (général)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from agent.llm_router import get_router


# ---------- types & spécialistes ----------

@dataclass
class Specialist:
    name:        str
    description: str
    provider:    str              # provider router (groq, intelx, etc.)
    model:       Optional[str] = None
    tool:        Optional[str] = None   # tool Jarvis associé (code_helper, dev_agent...)
    keywords:    list[str] = field(default_factory=list)


SPECIALISTS: dict[str, Specialist] = {
    "code": Specialist(
        name="Code Generator",
        description="Génère/corrige/édite un fichier de code (script unique).",
        provider="cerebras",           # ultra rapide pour code court
        model="llama3.1-8b",
        tool="code_helper",
        keywords=["code", "script", "function", "fonction", "écris", "write",
                  "fix", "corrige", "debug", "optimize"],
    ),
    "build_project": Specialist(
        name="Project Builder",
        description="Construit un projet complet multi-fichiers (jeu, app, etc.).",
        provider="groq",
        model="llama-3.3-70b-versatile",
        tool="dev_agent",
        keywords=["build", "projet", "project", "app", "application", "jeu",
                  "game", "snake", "tetris", "demineur", "minesweeper",
                  "site", "website", "make"],
    ),
    "osint": Specialist(
        name="OSINT Researcher",
        description="Recherche leaks, dark web, pastes, documents, whois.",
        provider="intelx",
        model="intelligence-x-search",
        keywords=["osint", "leak", "breach", "dark web", "darkweb", "paste",
                  "dox", "recon", "email", "@", "intelx"],
    ),
    "people": Specialist(
        name="People Finder",
        description="Nom+prénom -> profils sociaux, usernames, emails, leaks.",
        provider="groq",
        model="llama-3.3-70b-versatile",
        tool="people_search",
        keywords=["qui est", "who is", "trouve infos", "find person",
                  "recherche personne", "profil", "nom prenom",
                  "people search", "find people", "investigate"],
    ),
    "cybersec": Specialist(
        name="Cybersec Assistant",
        description="Pentest, exploit dev, analyse vuln (uncensored).",
        provider="groq",               # fallback si pas de kindo/venice
        model="llama-3.3-70b-versatile",
        keywords=["pentest", "exploit", "vuln", "cve", "shellcode", "payload",
                  "hack", "bypass", "reverse", "rce", "xss", "sqli"],
    ),
    "research": Specialist(
        name="Web Researcher",
        description="Recherche web + synthèse LLM.",
        provider="groq",
        model="llama-3.3-70b-versatile",
        tool="web_search",
        keywords=["search", "recherche", "trouve", "find", "actualité",
                  "news", "today", "aujourd'hui"],
    ),
    "reasoning": Specialist(
        name="Deep Reasoner",
        description="Raisonnement profond, math, logique.",
        provider="openrouter",
        model="deepseek/deepseek-r1:free",
        keywords=["raisonne", "reason", "prouve", "math", "théorème",
                  "logique", "step by step", "explique pourquoi"],
    ),
    "creative": Specialist(
        name="Creative Writer",
        description="Écriture créative, histoires, poèmes.",
        provider="mistral",
        model="mistral-large-latest",
        keywords=["écrit", "histoire", "story", "poème", "poem", "créatif",
                  "creative", "scénario"],
    ),
    "vision": Specialist(
        name="Vision Analyzer",
        description="Analyse image / screenshot.",
        provider="gemini",
        model="gemini-2.5-flash",
        keywords=["image", "screenshot", "capture", "analyse l'écran",
                  "voir l'écran"],
    ),
    "chat": Specialist(
        name="General Chat",
        description="Conversation générale, fallback router.",
        provider="groq",
        model="llama-3.3-70b-versatile",
        keywords=[],
    ),
}


# ---------- classifier ----------

_CLASSIFY_SYSTEM = """Tu es un classifieur de tâches. Étant donné une requête utilisateur,
retourne UNIQUEMENT un JSON de la forme:
{"type": "<type>", "confidence": <0-1>, "reason": "<courte raison>"}

Types valides:
- code          : écrire/corriger/éditer UN fichier de code
- build_project : construire un PROJET multi-fichiers (jeu, app, site)
- osint         : recherche de leaks/email/domaine/IP (Intelligence X)
- cybersec      : pentest, exploit, vulnérabilité (attaque/défense)
- research      : recherche web d'info factuelle récente
- reasoning     : problème qui demande raisonnement profond (maths, logique)
- creative      : écriture créative (histoire, poème)
- vision        : analyse d'image / screenshot
- chat          : conversation générale, question simple

Réponds UNIQUEMENT le JSON, rien d'autre."""


def classify(prompt: str) -> dict:
    """Retourne {'type': str, 'confidence': float, 'reason': str}."""
    # 1) heuristique rapide par mots-clés avant LLM (économise appels)
    low = prompt.lower()
    for key, spec in SPECIALISTS.items():
        if any(kw in low for kw in spec.keywords if len(kw) >= 4):
            return {"type": key, "confidence": 0.7, "reason": "keyword match"}

    # 2) LLM classifier (rapide : groq/cerebras)
    try:
        raw = get_router().generate(
            prompt=f"Requête: {prompt}\n\nJSON:",
            system=_CLASSIFY_SYSTEM,
            temperature=0.0,
            max_tokens=200,
        )
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        t = data.get("type", "chat")
        if t not in SPECIALISTS:
            t = "chat"
        return {
            "type":       t,
            "confidence": float(data.get("confidence", 0.5)),
            "reason":     data.get("reason", ""),
        }
    except Exception as e:
        return {"type": "chat", "confidence": 0.0, "reason": f"fallback: {e}"}


# ---------- planner ----------

def plan(prompt: str, task_type: str) -> list[dict]:
    """Retourne une liste d'étapes {description, tool?, params?} adaptée au type."""
    spec = SPECIALISTS.get(task_type, SPECIALISTS["chat"])

    # Missions longues (build_project) → déjà gérées par agent.planner
    if task_type == "build_project":
        return [{
            "description": f"Build project: {prompt}",
            "tool":        "dev_agent",
            "parameters":  {"description": prompt, "language": "python"},
            "specialist":  spec.name,
        }]

    # Code court → 1 step
    if task_type == "code":
        return [{
            "description": f"Write code: {prompt}",
            "tool":        "code_helper",
            "parameters":  {"description": prompt, "action": "write"},
            "specialist":  spec.name,
        }]

    # People → pipeline people_search complet
    if task_type == "people":
        return [{
            "description": f"People search: {prompt}",
            "tool":        "people_search",
            "parameters":  {"name": prompt, "deep": True},
            "specialist":  spec.name,
        }]

    # OSINT → recherche directe IntelX
    if task_type == "osint":
        target = _extract_osint_target(prompt)
        return [{
            "description": f"OSINT lookup: {target}",
            "tool":        "__router_direct__",
            "parameters":  {"provider": "intelx", "query": target},
            "specialist":  spec.name,
        }]

    # Research → web search + synthèse
    if task_type == "research":
        return [
            {"description": f"Web search: {prompt}", "tool": "web_search",
             "parameters": {"query": prompt}, "specialist": "Searcher"},
            {"description": "Synthèse LLM", "tool": "__router_direct__",
             "parameters": {"provider": spec.provider, "model": spec.model},
             "specialist": spec.name},
        ]

    # Default : direct LLM sur le bon provider
    return [{
        "description": prompt,
        "tool":        "__router_direct__",
        "parameters":  {"provider": spec.provider, "model": spec.model},
        "specialist":  spec.name,
    }]


def _extract_osint_target(prompt: str) -> str:
    """Extrait email/domain/IP/username du prompt pour IntelX."""
    # email
    m = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", prompt)
    if m: return m.group(0)
    # IP
    m = re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", prompt)
    if m: return m.group(0)
    # domain
    m = re.search(r"\b[\w\-]+\.[a-z]{2,}\b", prompt, re.I)
    if m: return m.group(0)
    # fallback : dernier mot utile
    return prompt.strip().split()[-1] if prompt.strip() else prompt


# ---------- dispatch ----------

def dispatch(
    prompt: str,
    tool_runner: Optional[Callable[[str, dict], str]] = None,
    speak:       Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Pipeline complet. Retourne:
    {
      "classification": {...},
      "plan":           [...],
      "results":        ["..."],
      "specialist":     "...",
    }
    """
    cls  = classify(prompt)
    task = cls["type"]
    spec = SPECIALISTS[task]

    print(f"[Dispatcher] 🧠 Type: {task} ({cls['confidence']:.0%}) — {cls['reason']}")
    print(f"[Dispatcher] 🎯 Specialist: {spec.name} via {spec.provider}/{spec.model}")
    # NB: pas de speak() ici — la voix appartient au turn principal (anti multi-réponse).

    steps   = plan(prompt, task)
    results = []

    for i, step in enumerate(steps, 1):
        desc = step.get("description", "")
        tool = step.get("tool")
        params = step.get("parameters", {})
        print(f"[Dispatcher] [{i}/{len(steps)}] {desc[:80]}")

        if tool == "__router_direct__":
            # appel LLM direct via router avec provider/model forcés
            out = get_router().generate(
                prompt=prompt,
                model=params.get("model"),
            )
        elif tool and tool_runner:
            out = tool_runner(tool, params)
        else:
            out = get_router().generate(prompt=desc)

        results.append(out)

    return {
        "classification": cls,
        "plan":           steps,
        "results":        results,
        "specialist":     spec.name,
    }


# ---------- singleton helpers ----------

def get_specialists() -> dict[str, Specialist]:
    return SPECIALISTS


def describe_specialists() -> str:
    """Résumé texte pour l'UI / logs."""
    lines = ["Spécialistes disponibles :"]
    for key, s in SPECIALISTS.items():
        lines.append(f"  • {key:14s} → {s.name:22s} [{s.provider}/{s.model}]")
    return "\n".join(lines)
