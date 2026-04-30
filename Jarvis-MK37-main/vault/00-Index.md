---
title: INDEX — JARVIS Mark XXXVII (MK37) Vault
date: 2026-04-29
tags: [jarvis, mk37, index, moc]
status: active
version: 1.0
---

# 🤖 JARVIS Mark XXXVII — Vault de Documentation

> **Vault dédié à la version MK37**. Distinct de [[claudeMEMOIR/obsidian]] qui couvre MK35.
> Code source : `Jarvis-MK37-main/`
> Vault doc : `Jarvis-MK37-main/vault/`

---

## 🚀 Démarrage rapide

- [[Docs/Project-Overview]] — vue d'ensemble MK37
- [[Docs/Differences-vs-MK35]] — ce qui change par rapport à MK35
- [[Operations/Setup-Env]] — installation + `.env`
- [[Architecture/Stack-Technique]] — dépendances + versions

## 🏛️ Architecture

- [[Architecture/Overview]] — vue technique globale
- [[Architecture/Agent-Dispatcher]] — classify → plan → specialist → execute
- [[Architecture/LLM-Router]] — multi-provider + fallback auto
- [[Architecture/Stack-Technique]] — Python 3.11+, Gemini Live, PyQt6, Vosk

## ✨ Features

### Cerveau & raisonnement
- [[Features/Specialists-9-Roles]] — coder, researcher, writer, planner, debugger, analyst, translator, summarizer, critic
- [[Features/Verifier-Agent]] — post-condition + LLM judge
- [[Features/Personality-System]] — 5 rôles (jarvis_classic / coach / tutor / hacker / therapist)

### Sécurité
- [[Features/Authority-Engine]] — gating allowlist/denylist/ask, audit JSONL

### Mémoire
- [[Features/Knowledge-Graph]] — SQLite entities/facts/relationships

### Audio & perception
- [[Features/Wake-Word]] — Porcupine / Vosk / openwakeword
- [[Features/Awareness-Pipeline]] — capture écran continue + détection stagnation

### Plateforme
- [[Features/Cross-Platform]] — Windows / macOS / Linux

### OSINT
- [[Features/OSINT-Tools]] — `people_search` + `online_presence_audit`

## 📖 Docs

- [[Docs/Project-Overview]]
- [[Docs/Actions-Tools]] — catalogue 21 tools
- [[Docs/Differences-vs-MK35]]

## 🔧 Operations

- [[Operations/Setup-Env]] — installation, `.env`, clés API

## 📝 Logs

- [[Logs/2026-04-29 — Vault MK37 init]]

---

## 🗂️ Structure physique

```
Jarvis-MK37-main/
├── main.py
├── ui.py / ui.html
├── actions/         (21 tools)
├── agent/           (dispatcher, router, authority, awareness, …)
├── memory/          (long_term.json, knowledge_graph.db, audit.log)
├── core/            (prompt.txt)
├── config/          (api_keys, authority, personality)
├── models/vosk/     (offline STT)
├── tests/
└── vault/           ← ce vault
    ├── 00-Index.md
    ├── Architecture/  (4)
    ├── Docs/          (3)
    ├── Features/      (9)
    ├── Operations/    (1)
    └── Logs/          (1)
```

---

## 📏 Règles du vault

1. Une note = un sujet atomique
2. Frontmatter YAML obligatoire (`title`, `date`, `tags`)
3. Liens `[[Folder/Name]]` systématiques — jamais de note orpheline
4. Runtime ≠ doc : fichiers `.json/.db/.log` de `memory/` **ne sont PAS** dans le vault
