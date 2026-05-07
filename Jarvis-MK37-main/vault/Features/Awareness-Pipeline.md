---
title: Awareness Pipeline — capture écran continue
date: 2026-04-29
tags: [feature, awareness, vision, mk37]
---

# Awareness Pipeline

> Thread continu : capture écran → hash → buffer → détection stagnation.
> Fichier : `agent/awareness.py`

---

## Boucle

```
every interval_s (default 10s):
    grab screen (mss)
       │
       ▼
    hash (sha1 du raw bytes)
       │
       ▼
    OCR léger (optionnel, pytesseract)
       │
       ▼
    push dans deque buffer
       │
       ▼
    si même hash N cycles consécutifs → flag struggle = True
```

---

## API

```python
from agent.awareness import AwarenessPipeline

pipe = AwarenessPipeline(interval_s=10.0, struggle_threshold=3)
pipe.start()

# Récupérer contexte
ctx = pipe.get_context()
# {"last_screen_hash": "...", "ocr_text": "...", "struggle": False}
```

---

## Fallback silencieux

Si `mss` ou `pytesseract` indispo → thread no-op, aucune erreur. Permet de runner Jarvis dans un container sans display.

---

## Use case

L'agent principal peut récupérer `awareness.get_context()` pour enrichir son prompt :
- Si `struggle: True` → propose de l'aide proactivement
- Texte OCR → contexte de ce que l'utilisateur regarde sans avoir besoin de demander un screenshot

---

## Liens

- [[Architecture/Overview]] — couche perception


## Liens Transverses
- [[08-Tools/tool-desktop_control-overview.md]]
- [[08-Tools/tool-web_search-params.md]]
