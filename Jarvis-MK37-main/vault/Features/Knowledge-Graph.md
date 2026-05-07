---
title: Knowledge Graph — SQLite sidecar
date: 2026-04-29
tags: [feature, memory, knowledge-graph, sqlite]
---

# Knowledge Graph

> Sidecar SQLite du `memory_manager` JSON. Coexiste, ne remplace pas.
> Fichier : `memory/knowledge_graph.py` — DB : `memory/knowledge_graph.db`

---

## Schéma

### `entities`
- `id` PK, `name`, `type` (default `'thing'`), `created_at`, UNIQUE(name, type)

### `facts`
- `id`, `entity_id` FK, `key`, `value`, `source`, `confidence` (0.0-1.0), `updated_at`

### `relationships`
- `id`, `src_id`, `dst_id`, `type` (works_at, friend_of, depends_on…), `weight`, `updated_at`

---

## API

```python
from memory.knowledge_graph import (
    add_entity, add_fact, link, search, get_entity, get_related
)

eid = add_entity("Hakob", "person")
add_fact(eid, "city", "Paris", source="user", confidence=1.0)

proj = add_entity("MK37", "project")
link(eid, proj, "owns", weight=1.0)

related = get_related(eid)
```

---

## Pourquoi en plus du JSON ?

| | `long_term.json` | `knowledge_graph.db` |
|---|---|---|
| Forme | clé/valeur plate | graphe relationnel |
| Requête | full scan | SQL indexé |
| Relations | non | first-class |
| Versioning | écrasement | confidence + updated_at |
| Usage | quick lookups | reasoning sur connections |

Alimenté notamment par le [[Features/Verifier-Agent]] (chaque verdict = fait loggué).

---

## Fallback

Si `sqlite3` indispo → no-op silencieux.

---

## Liens

- [[Architecture/Overview]]
- [[Features/Verifier-Agent]]


## Liens Transverses
- [[Architecture/Stack-Technique.md]]
- [[07-LLM-Router/router-overview.md]]
