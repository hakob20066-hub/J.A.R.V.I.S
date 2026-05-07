---
title: Agent Dispatcher
date: 2026-04-29
tags: [architecture, agent, dispatcher, mk37]
---

# Agent Dispatcher

> Cerveau orchestrateur multi-agents.
> Fichier : `agent/agent_dispatcher.py`
> Liens : [[Architecture/LLM-Router]] | [[Features/Specialists-9-Roles]] | [[Architecture/Overview]]

---

## Pipeline

```
prompt
  │
  ▼
classify(prompt)        ──► task type
  │
  ▼
plan(prompt, type)      ──► step-by-step plan
  │
  ▼
select_specialist(type) ──► (agent, model, provider)
  │
  ▼
execute(plan)           ──► résultat
```

---

## Types de tâche reconnus

| Type | Agent | Provider |
|------|-------|----------|
| `code` | code_helper (un fichier) | cerebras |
| `build_project` | dev_agent (multi-fichiers) | claude |
| `osint` | intelx (leaks, dark web) | intelx |
| `cybersec` | kindo / venice (uncensored) | venice |
| `research` | web_search + LLM | gemini |
| `reasoning` | deepseek-r1 | deepseek |
| `creative` | mistral (créatif UE) | mistral |
| `vision` | gemini (image) | gemini |
| `chat` | fallback router | router default |

---

## Spécialiste = dataclass

```python
@dataclass
class Specialist:
    name:        str
    description: str
    provider:    str
    model:       Optional[str] = None
    tool:        Optional[str] = None
    keywords:    list[str] = field(default_factory=list)
```

Le dispatcher mappe `task_type → Specialist`, puis délègue au tool direct **ou** au LLM Router.

---

## Différence avec `delegate_task`

- **Dispatcher** = routage automatique (Jarvis classifie tout seul)
- **delegate_task** = appel explicite (ex : "demande au coder de…")

Les deux passent par le [[Architecture/LLM-Router]].

---

## Liens

- [[Architecture/LLM-Router]]
- [[Features/Specialists-9-Roles]]
- [[Architecture/Overview]]


## Liens Transverses
- [[Architecture/Overview.md]]
- [[Docs/Phase-Prompts-v2.md]]
