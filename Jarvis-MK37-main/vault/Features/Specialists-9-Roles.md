---
title: Specialists — 9 sous-agents délégables
date: 2026-04-29
tags: [feature, agents, specialists, mk37]
---

# Specialists — 9 rôles

> Invocables via `delegate_task` ou auto-routés par le [[Architecture/Agent-Dispatcher]].
> Fichier : `agent/specialists.py`

---

## Liste

| Rôle | Modèle préféré | Usage |
|------|----------------|-------|
| **coder** | claude-sonnet-4-6 | Code production, diffs minimaux |
| **researcher** | gemini-2.5-flash | Brief structuré (TL;DR + sources), flag uncertainty |
| **writer** | claude-sonnet-4-6 | Texte pro, ton adapté |
| **planner** | gemini-2.5-flash-lite | Plan ≤ 50 étapes JSON |
| **debugger** | claude-sonnet-4-6 | `{cause, fix, patch}` à partir d'erreur |
| **analyst** | _(défaut router)_ | Analyse données / tableaux |
| **translator** | _(défaut router)_ | Traduction multi-langues |
| **summarizer** | _(défaut router)_ | Résumé compact |
| **critic** | _(défaut router)_ | Revue / critique constructive |

Le routage passe par le [[Architecture/LLM-Router]] → fallback multi-provider gratuit auto.

---

## API

```python
from agent.specialists import delegate, list_specialists

print(list_specialists())
# ['coder', 'researcher', 'writer', 'planner', 'debugger', ...]

result = delegate(role="coder", task="Write a bash script that ...")
```

---

## Invocation

### Explicite
```
delegate_task(role="coder", task="...", context="...")
```

### Implicite
Le [[Architecture/Agent-Dispatcher]] classifie et sélectionne.

---

## Liens

- [[Architecture/Agent-Dispatcher]]
- [[Architecture/LLM-Router]]
- [[Docs/Actions-Tools]]


## Liens Transverses
- [[01-Concepts/concept-foreground-interrupt.md]]
- [[01-Concepts/concept-lru-cache.md]]
