---
title: OSINT Tools — people_search + online_presence_audit
date: 2026-04-29
tags: [feature, osint, mk37]
---

# OSINT Tools

> Deux pipelines OSINT pour profiler une personne à partir d'un nom ou d'un Instagram.
> Fichiers : `actions/people_search.py`, `actions/online_presence_audit.py`

---

## `people_search` — Pipeline complet

Entrée : `nom + prénom`

### Étapes

1. **Normalisation** — ascii, slugs, génération de usernames candidats
2. **Google dorks parallèles** — linkedin, facebook, instagram, twitter/x, github, tiktok, youtube, pages blanches
3. **Scan username multi-sites** — sherlock-lite, HTTP HEAD requests
4. **Génération emails permutés** — `prenom.nom@gmail/outlook/yahoo/hotmail/proton`
5. **Vérif Gravatar** — MD5(email) → check existence
6. **Chaîne IntelX** sur chaque email trouvé (si clé API présente)
7. **Rapport synthétique**

### Pas de clé requise
DuckDuckGo + HEAD publics. IntelX optionnel pour dark web / leaks / pastes.

---

## `online_presence_audit` — Audit Instagram

Entrée : `@handle Instagram` (+ aliases optionnels)

Recherche tous les comptes publics liés (mêmes pseudos sur d'autres plateformes).

```python
from actions.online_presence_audit import online_presence_audit

result = online_presence_audit(
    instagram_handle="@johndoe",
    aliases=["jdoe", "jd92"]
)
# { "confirmed": [...], "probable": [...], "uncertain": [...] }
```

---

## Authority gating

Ces tools ne sont pas dans la `allowlist` par défaut → l'[[Features/Authority-Engine]] peut les forcer en `ask` selon `mode`. À utiliser de manière responsable.

---

## Liens

- [[Docs/Actions-Tools]]
- [[Features/Authority-Engine]]
