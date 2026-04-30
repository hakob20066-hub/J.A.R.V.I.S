---
title: Project Overview — JARVIS Mark XXXVII
date: 2026-04-29
tags: [docs, overview, mk37]
priority: high
---

# Project Overview — MK37

> Liens : [[Architecture/Overview]] | [[Docs/Differences-vs-MK35]] | [[Operations/Setup-Env]]

---

## Pitch

Real-time voice AI qui voit, entend, comprend et contrôle l'OS. Tourne sur **Windows, macOS, Linux**. Local-first, zéro abonnement. Conçu par **FatihMakes** comme évolution la plus polyvalente du projet Jarvis.

---

## Capacités

| Domaine | Détail |
|---------|--------|
| 🎙️ Voice | Gemini 2.5 Flash native audio (Live API), latence ultra-faible |
| 🖥️ System control | Lance apps, gère fichiers, exécute commandes shell |
| 🧩 Autonomous tasks | Planning multi-étapes via [[Architecture/Agent-Dispatcher]] |
| 👁️ Visual awareness | Screen processing continu ([[Features/Awareness-Pipeline]]) |
| 🧠 Persistent memory | JSON long-term + [[Features/Knowledge-Graph]] SQLite |
| 🔒 Privacy first | Mute physique (F4 / UI), [[Features/Authority-Engine]] |
| ⌨️ Voice & keyboard | Switch fluide entre les deux |
| 🌍 Cross-platform | Windows / macOS / Linux ([[Features/Cross-Platform]]) |

---

## Stack

- **Python 3.11/3.12**
- **Gemini 2.5 Flash native audio** (Live API, voice principal)
- **Multi-provider LLM** : Anthropic, OpenAI, Gemini, DeepSeek, OpenRouter, Groq, Ollama
- **PyQt6 + qtpy + pywebview** (UI)
- **Playwright + pyautogui + pywinauto** (browser/GUI)
- **Vosk + Porcupine + openwakeword** (wake word, 3 backends)
- **sqlite3** (knowledge graph)
- **PyYAML** (personality config)
- **python-dotenv** (.env)

Détails : [[Architecture/Stack-Technique]]

---

## Quick start

```bash
git clone <repo>
cd Jarvis-MK37-main
cp .env.example .env       # remplir GEMINI_API_KEY au minimum
pip install -r requirements.txt
playwright install
python main.py
```

Voir [[Operations/Setup-Env]] pour les détails.

---

## Liens

- [[00-Index]]
- [[Architecture/Overview]]
- [[Docs/Actions-Tools]]
- [[Docs/Differences-vs-MK35]]
