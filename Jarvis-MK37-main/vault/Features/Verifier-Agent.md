---
title: Verifier Agent — post-condition + LLM judge
date: 2026-04-29
tags: [feature, verifier, agent, mk37]
---

# Verifier Agent

> Vérifie chaque tool call, indépendamment de l'Executor. Détecte les fausses réussites.
> Fichier : `agent/verifier.py` + `agent/post_conditions.py`

---

## Pipeline

```
1. Post-condition codable      ← psutil / pathlib / pygetwindow
   (ex: open_app("Chrome") → vérif fenêtre Chrome existe)
       │ inconclusive
       ▼
2. LLM judge (modèle léger)    ← prompt critic court
   "Le tool a-t-il atteint son objectif ?"
       │
       ▼
3. Verdict : PASS | FAIL | UNSURE  + raison + suggestion
       │
       ▼
4. Log dans le KG ([[Features/Knowledge-Graph]])
   → fact réutilisable (skill memory)
```

---

## Verdict

```python
@dataclass
class Verdict:
    status: str          # PASS | FAIL | UNSURE
    confidence: float    # 0.0 - 1.0
    reason: str
    suggestion: str = ""
```

---

## Usage

```python
from agent.verifier import get_verifier

v = get_verifier()
verdict = v.verify(goal, tool, params, result)

if verdict.status == "FAIL":
    # retry, escalate, ou abandonner
    ...
```

---

## Pourquoi indépendant de l'Executor ?

L'executor reporte "succès" si la fonction tool n'a pas levé d'exception. Mais ça ne prouve pas que **l'objectif** a été atteint :

- `open_app("Chrome")` ne lève pas → mais la fenêtre n'apparaît jamais
- `file_controller(write)` ne lève pas → mais le fichier est vide
- `web_search` ne lève pas → mais retourne 0 résultat utile

Le Verifier observe l'**état du monde** après le tool call.

---

## Liens

- [[Architecture/Overview]]
- [[Features/Knowledge-Graph]]
- [[Features/Authority-Engine]]
