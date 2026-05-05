---
title: Setup & Environnement — MK37
date: 2026-04-29
tags: [operations, setup, env, configuration]
priority: high
---

# Setup & Environnement

> Installation, fichier `.env`, configs. Référence pour le setup d'un nouveau PC.

---

## 1. Cloner

```bash
git clone <repo>
cd Jarvis-MK37-main
```

## 2. `.env` — clés API

```bash
cp .env.example .env
```

Éditer `.env` :

```env
GEMINI_API_KEY=<obligatoire>
ANTHROPIC_API_KEY=<optionnel>
OPENAI_API_KEY=<optionnel>
DEEPSEEK_API_KEY=<optionnel>
OPENROUTER_API_KEY=<optionnel>
GROQ_API_KEY=<optionnel>
OS_SYSTEM=windows                # ou macos / linux
```

> **Important** : `.env` est dans `.gitignore`, jamais commité.

## 3. Dépendances

### Recommandé
```bash
python setup.py
```

### Manuel
```bash
pip install -r requirements.txt
playwright install
```

## 4. Lancer

```bash
python main.py
```

---

## Configs additionnelles

### `config/api_keys.json`
Fallback si pas de `.env`. Le [[Architecture/LLM-Router]] lit en priorité `.env`, puis ce JSON.

### `config/authority.json`
Politique de gating ([[Features/Authority-Engine]]). Modifier `mode` (`paranoid` / `balanced` / `autonomous`) selon la confiance accordée.

### `config/personality.yaml`
Rôle actif ([[Features/Personality-System]]). Changer `active_role` puis redémarrer.

### `core/prompt.txt`
System prompt principal. Modifier pour ajuster le comportement de fond.

### `models/vosk/`
Modèle Vosk pour wake word offline. À télécharger manuellement ([[Features/Wake-Word]]).

---

## Problèmes courants

| Erreur | Solution |
|--------|----------|
| `GEMINI_API_KEY not found` | Vérifier `.env` ou `config/api_keys.json` |
| `Import error: dotenv` | `pip install python-dotenv` |
| Playwright | `playwright install` |
| `comtypes` / `pycaw` errors (non-Windows) | Normal, ces libs sont Win-only |
| Pas de wake word | Installer Vosk ou ajouter clé Porcupine |

---

## Hiérarchie de chargement des clés

```
1. variables d'environnement OS
2. fichier .env (loaded by python-dotenv)
3. config/api_keys.json (fallback)
4. erreur si rien trouvé
```

Le [[Architecture/LLM-Router]] essaye chaque provider et passe au suivant si la clé manque ou échoue.

---

## Liens

- [[Architecture/Stack-Technique]]
- [[Features/Cross-Platform]]
- [[Architecture/LLM-Router]]


## Liens Transverses
- [[01-Concepts/concept-emotional-valence.md]]
- [[01-Concepts/concept-async-notification.md]]
