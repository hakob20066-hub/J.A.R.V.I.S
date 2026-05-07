---
title: Architecture Overview — MK37
date: 2026-04-29
tags: [architecture, overview, mk37]
priority: high
---

# Architecture Overview

> Vue technique globale. Chaque composant a sa note dédiée.
> Liens : [[Docs/Project-Overview]] | [[Architecture/Stack-Technique]]

---

## Diagramme

```
                 ┌────────────────────────┐
                 │   PyQt6 / pywebview UI │  ←── ui.html
                 │   + ui.py              │
                 └─────────┬──────────────┘
                           │ events
                           ▼
   ┌────────────────────────────────────────────────────┐
   │  main.py — Gemini Live Audio Loop                  │
   │  • LiveConnectConfig + function_declarations       │
   │  • Mic capture (sounddevice 16 kHz)                │
   │  • Audio out (24 kHz)                              │
   └─────────┬──────────────────────────────────────────┘
             │ tool calls
             ▼
   ┌────────────────────────────────────────────────────┐
   │  Authority Engine ([[Features/Authority-Engine]])  │
   │  allow / ask / deny + audit JSONL                  │
   └─────────┬──────────────────────────────────────────┘
             │ approved
             ▼
   ┌────────────────────────────────────────────────────┐
   │  Agent Dispatcher ([[Architecture/Agent-Dispatcher]])│
   │  classify → plan → specialist → execute            │
   └─────────┬──────────────────────────────────────────┘
             │
   ┌─────────┴────────────┐
   ▼                      ▼
[Direct tool]       [LLM Router] ([[Architecture/LLM-Router]])
actions/*.py        ↓
                    Anthropic / OpenAI / Gemini /
                    DeepSeek / OpenRouter / Groq / Ollama
                    (fallback auto sur quota / 429)
             │
             ▼
   ┌────────────────────────────────────────────────────┐
   │  Verifier ([[Features/Verifier-Agent]])            │
   │  post-conditions + LLM judge → PASS/FAIL/UNSURE    │
   └─────────┬──────────────────────────────────────────┘
             │ result + verdict
             ▼
   ┌────────────────────────────────────────────────────┐
   │  Memory                                            │
   │  • long_term.json (memory_manager)                 │
   │  • knowledge_graph.db ([[Features/Knowledge-Graph]])│
   │  • authority_audit.log                             │
   └────────────────────────────────────────────────────┘

         ┌───────────────────────────────────┐
         │  Background threads               │
         │  • Wake word ([[Features/Wake-Word]])│
         │  • Awareness ([[Features/Awareness-Pipeline]])│
         │  • UI tracker                     │
         └───────────────────────────────────┘
```

---

## Composants principaux

### 1. Voice loop (`main.py`)
Gemini 2.5 Flash native audio Live API. Mic 16 kHz → Gemini → audio 24 kHz + tool calls.

### 2. Tool dispatch (`agent/executor.py`)
Reçoit le tool call de Gemini, traverse l'[[Features/Authority-Engine|Authority Engine]] puis exécute via le [[Architecture/Agent-Dispatcher|Dispatcher]].

### 3. LLM Router (`agent/llm_router.py`)
Routage multi-provider avec fallback automatique sur quota / 429 / rate-limit. Voir [[Architecture/LLM-Router]].

### 4. Specialists (`agent/specialists.py`)
9 sous-agents invoqués via le tool `delegate_task`. Voir [[Features/Specialists-9-Roles]].

### 5. Verifier (`agent/verifier.py`)
Vérifie chaque tool call indépendamment de l'executor. Voir [[Features/Verifier-Agent]].

### 6. Memory
- `memory/memory_manager.py` — JSON long-term (préférences, identité, projets)
- `memory/knowledge_graph.py` — SQLite entities + facts + relationships

### 7. Awareness (`agent/awareness.py`)
Thread continu : capture écran → hash → buffer. Détecte la stagnation (même fenêtre N cycles).

### 8. Wake word (`agent/wake_word.py`)
3 backends : Porcupine → Vosk → openwakeword.

---

## Threading

| Thread | Rôle |
|--------|------|
| Main | UI Qt event loop |
| `jarvis-live` | Boucle Gemini Live (asyncio) |
| `awareness` | Capture écran périodique |
| `wake-word` | Listener mic continu |
| `mission-runner` | (deprecated 2026-04-25, voir `mission_models.py`) |

---

## Liens

- [[Architecture/Stack-Technique]]
- [[Architecture/Agent-Dispatcher]]
- [[Architecture/LLM-Router]]
- [[Features/Authority-Engine]]
- [[Docs/Project-Overview]]


## Liens Transverses
- [[08-Tools/tool-shutdown_jarvis-edge-cases.md]]
- [[08-Tools/tool-dev_agent-overview.md]]
