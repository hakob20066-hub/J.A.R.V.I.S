---
title: Vault MK37 — initialisation
date: 2026-04-29
tags: [log, vault, init, mk37]
---

# Log — Vault MK37 init (2026-04-29)

> Création du vault de documentation pour la version Mark XXXVII.
> Aucun vault n'existait pour MK37 (le précédent vault `claudeMEMOIR/obsidian` couvre MK35).

---

## Structure créée

```
vault/
├── 00-Index.md                 ← MOC
├── Architecture/
│   ├── Overview.md
│   ├── Agent-Dispatcher.md
│   ├── LLM-Router.md
│   └── Stack-Technique.md
├── Docs/
│   ├── Project-Overview.md
│   ├── Differences-vs-MK35.md
│   └── Actions-Tools.md
├── Features/
│   ├── Authority-Engine.md
│   ├── Specialists-9-Roles.md
│   ├── Knowledge-Graph.md
│   ├── Awareness-Pipeline.md
│   ├── Wake-Word.md
│   ├── Personality-System.md
│   ├── Verifier-Agent.md
│   ├── OSINT-Tools.md
│   └── Cross-Platform.md
├── Operations/
│   └── Setup-Env.md
└── Logs/
    └── 2026-04-29 — Vault MK37 init.md   ← ce fichier
```

**Total** : 18 notes initiales.

---

## Sources analysées

- `readme.md` — pitch + capacités
- `INSTALLATION.md` — setup
- `requirements.txt` — stack
- `config/personality.yaml` — 5 rôles
- `config/authority.json` — defaults gating
- `agent/agent_dispatcher.py` — pipeline 4 étapes
- `agent/llm_router.py` — 7 providers, hiérarchie
- `agent/authority.py` — modes et audit
- `agent/specialists.py` — 9 rôles
- `agent/awareness.py` — pipeline screen
- `agent/verifier.py` — verdict pipeline
- `agent/wake_word.py` — 3 backends
- `memory/knowledge_graph.py` — schéma SQLite
- `actions/*.py` — 21 tools listés
- `main.py` (header) — config Live API

---

## Différences architecturales clés vs MK35

Voir [[Docs/Differences-vs-MK35]] pour le tableau complet. TL;DR :

- **MK37 = système multi-agents** (dispatcher + 9 specialists)
- **MK37 = multi-provider** (7 LLMs au lieu de Gemini+Mistral)
- **MK37 = sécurité explicite** (Authority Engine)
- **MK37 = vérification** (Verifier post-action)
- **MK37 = cross-platform** (Win + macOS + Linux)
- **MK37 = .env first** (au lieu de api_keys.json only)

---

## TODO futur

- [ ] Tester le wake word Vosk avec un modèle FR
- [ ] Documenter les missions (file `mission_models.py` flag deprecated, à clarifier)
- [ ] Snapshot de la `knowledge_graph.db` après quelques sessions
- [ ] Logger les premiers `authority_audit.log` parsés

---

## Liens

- [[00-Index]]
- [[Docs/Project-Overview]]
- [[Docs/Differences-vs-MK35]]
