---
title: Différences MK37 vs MK35
date: 2026-04-29
tags: [docs, comparison, mk37, mk35]
priority: high
---

# Différences MK37 vs MK35

> Référence rapide pour comprendre ce qui change entre les deux versions.
> Liens : [[Docs/Project-Overview]] | [[Architecture/Overview]]

---

## Tableau comparatif

| Catégorie | MK35 | MK37 |
|-----------|------|------|
| **OS support** | Windows seulement | Windows + macOS + Linux ([[Features/Cross-Platform]]) |
| **LLM providers** | Gemini + Mistral fallback hardcodé | 7 providers via [[Architecture/LLM-Router]] |
| **Sub-agents** | aucun | 9 spécialistes ([[Features/Specialists-9-Roles]]) |
| **Permissions** | aucune | [[Features/Authority-Engine]] avec 3 modes |
| **Verification** | optimiste | [[Features/Verifier-Agent]] post-condition + LLM judge |
| **Memory** | JSON 3-couches + Obsidian vault | JSON + [[Features/Knowledge-Graph]] SQLite |
| **Awareness** | screen on demand | Pipeline continu + détection stagnation |
| **Wake word** | clap detector | Porcupine / Vosk / openwakeword ([[Features/Wake-Word]]) |
| **Personality** | hardcodée prompt.txt | YAML 5 rôles ([[Features/Personality-System]]) |
| **OSINT** | absent | `people_search` + `online_presence_audit` |
| **UI** | pywebview + index.html | PyQt6 + ui.html |
| **Config** | api_keys.json | `.env` + api_keys.json + authority.json + personality.yaml |
| **Mission system** | absent | présent (mais flag deprecated 2026-04-25 dans `mission_models.py`) |
| **Circuit breaker** | `infra/circuit_breaker.py` | intégré dans `llm_router.cooldown_seconds` |

---

## Ce qui a été supprimé

- `infra/` (circuit_breaker, retry, audio I/O autonome) → fusionné dans `agent/`
- `core/orchestrator.py` + `core/scheduler.py` + `core/planner.py` → simplifié, le dispatcher prend la main
- Mistral fallback hardcodé → remplacé par fallback chain LLM Router
- `Jarvis/` vault Obsidian intégré au repo → externe à reproduire (ce vault)

---

## Ce qui a été ajouté

- `agent/agent_dispatcher.py` (orchestrateur classify→plan→specialist)
- `agent/llm_router.py` (multi-provider)
- `agent/authority.py` (gating)
- `agent/specialists.py` (9 rôles)
- `agent/awareness.py` (screen capture loop)
- `agent/verifier.py` (post-condition + LLM judge)
- `agent/wake_word.py` (Porcupine / Vosk / OpenWakeWord)
- `agent/personality.py` + `config/personality.yaml`
- `memory/knowledge_graph.py` + `.db`
- `actions/delegate_task.py`, `actions/people_search.py`, `actions/online_presence_audit.py`, `actions/morning_briefing.py`, `actions/close_app.py`
- `models/vosk/` (offline STT)
- `tests/test_mission_store.py` (premiers tests unitaires)

---

## Migration mentale

Pour un dev qui connaît MK35 :

1. **Plus de `Mistral fallback`** → tout passe par `agent/llm_router.py`
2. **Plus d'`orchestrator` central** → `agent_dispatcher` classifie et délègue
3. **Plus de "tool exécuté direct"** → tout traverse l'`Authority Engine` puis le `Verifier`
4. **Plus de hardcode `C:\Users\hakob\Desktop\claudeMEMOIR`** → vault local au repo, pas de chemin absolu

---

## Liens

- [[00-Index]]
- [[Architecture/Overview]]
- [[Docs/Project-Overview]]
- [[Operations/Setup-Env]]
