---
title: Wake Word Detector — 3 backends
date: 2026-04-29
tags: [feature, audio, wake-word, mk37]
---

# Wake Word Detector

> Activation par mot-clé "jarvis" / "hey jarvis". 3 backends, fallback silencieux si rien dispo.
> Fichier : `agent/wake_word.py`

---

## Priorité décroissante

| Rang | Backend | Caractéristiques |
|------|---------|------------------|
| 1 | **Porcupine** (picovoice) | "jarvis" built-in, requires access key. Précis et rapide. |
| 2 | **Vosk** | STT offline, match "jarvis" dans le texte. 100 % gratuit, pas de compte. |
| 3 | **openwakeword** | Modèle ONNX, "hey_jarvis" par défaut (custom possible). |

---

## Setup

### Porcupine (option payante après free tier)
```json
// config/api_keys.json
{ "picovoice_access_key": "..." }
```

### Vosk (recommandé, gratuit)
```bash
# Télécharger un modèle (FR ou EN)
mkdir -p models/vosk
cd models/vosk
wget https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip
unzip vosk-model-small-fr-0.22.zip
```

### openwakeword
Auto-loaded si installé : `pip install openwakeword`

---

## Fallback

Si **aucun** backend dispo (pas de clé Porcupine, pas de modèle Vosk, pas d'openwakeword) → thread no-op. Activation manuelle uniquement (UI / hotkey).

---

## Liens

- [[Architecture/Overview]] — couche audio
- [[Operations/Setup-Env]] — config détaillée


## Liens Transverses
- [[08-Tools/tool-code_helper-edge-cases.md]]
- [[08-Tools/tool-agent_task-params.md]]
