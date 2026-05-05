---
title: Stack Technique — MK37
date: 2026-04-29
tags: [architecture, stack, dependencies]
---

# Stack Technique

> Référence des dépendances et versions.
> Liens : [[Architecture/Overview]] | [[Operations/Setup-Env]]

---

## Runtime

- **Python** 3.11 ou 3.12
- **OS** : Windows 10/11, macOS, Linux ([[Features/Cross-Platform]])
- **Microphone** requis

---

## Dépendances (`requirements.txt`)

### Audio
- `sounddevice` — capture mic 16 kHz

### LLM SDKs
- `google-genai`, `google-generativeai` — Gemini Live + REST
- `openai` — GPT-4o et compatibles (DeepSeek aussi)
- `anthropic` — Claude

### UI
- `PyQt6` + `qtpy` — UI native cross-platform
- `pywebview` — vue web embarquée

### Browser & GUI
- `playwright` — auto navigateur
- `pyautogui`, `pyperclip`, `pygetwindow`, `pywinauto` — auto OS

### Vision & écran
- `opencv-python`, `mss`, `Pillow`, `numpy`

### Système Windows
- `comtypes`, `pycaw` — audio devices
- `win10toast` — notifs
- `psutil` — process info
- `send2trash` — corbeille

### Web & data
- `requests`, `beautifulsoup4`, `duckduckgo-search`, `youtube-transcript-api`

### Config
- `python-dotenv` — `.env` loader *(NEW MK37)*
- `PyYAML` — `personality.yaml` *(NEW MK37)*

---

## Modèle vocal principal

`models/gemini-2.5-flash-native-audio-preview-12-2025` (Gemini Live API)

| Param | Valeur |
|-------|--------|
| Sample rate in | 16 kHz |
| Sample rate out | 24 kHz |
| Chunk size | 1024 samples |
| Voice | configurable (cf [[Features/Personality-System]]) |

---

## Wake word backends ([[Features/Wake-Word]])

- **Porcupine** (picovoice) — keyword "jarvis" built-in, requires access key
- **Vosk** — STT offline, modèle dans `models/vosk/`
- **openwakeword** — modèle ONNX, "hey_jarvis" par défaut

---

## Stockage local

| Fichier | Rôle |
|---------|------|
| `memory/long_term.json` | Identité, prefs, projets (JSON) |
| `memory/knowledge_graph.db` | SQLite (entities/facts/relationships) |
| `memory/authority_audit.log` | Audit JSONL append-only |
| `memory/missions.json` + `missions_log.jsonl` | (deprecated 2026-04-25) |

---

## Config files

| Fichier | Rôle |
|---------|------|
| `.env` | Clés API (prioritaire) — *NEW MK37* |
| `config/api_keys.json` | Clés API (fallback) |
| `config/authority.json` | Gating policy ([[Features/Authority-Engine]]) |
| `config/personality.yaml` | Rôles + tone ([[Features/Personality-System]]) |
| `core/prompt.txt` | System prompt principal |

Détails : [[Operations/Setup-Env]]

---

## Liens

- [[Architecture/Overview]]
- [[Operations/Setup-Env]]
- [[Features/Cross-Platform]]


## Liens Transverses
- [[08-Tools/tool-flight_finder-params.md]]
- [[01-Concepts/concept-system-prompt.md]]
