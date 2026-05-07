---
title: Phase 7.6 — 4 analyseurs cross-cutting
date: 2026-05-07
tags: [phase7.6, analyzers, behavior, session4]
parent_moc: [[00-MOC/MOC-OSINT]]
---

# 4 Analyzers cross-cutting

Exécutés après la cascade pivot (step 5b de `OSINTEngine.lookup_async`).
Entrée : `list[Finding]` → Sortie : dict stocké dans `OSINTReport.analyzers`.

```python
from agent.osint.analyzers import run_all
results = run_all(findings)  # → {behavior, network, historical, metadata}
```

Dossier : `agent/osint/analyzers/`

---

## BehaviorAnalyzer — `behavior.py`

Profil comportemental depuis les textes et timestamps des findings.

| Champ | Calcul |
|-------|--------|
| `timezone_hint` | heure la plus fréquente dans les timestamps |
| `language` | mots FR vs EN dans les textes extraits |
| `cadence` | posts/jour moyen |
| `topics` | mots-clés fréquents (hors stopwords) |
| `activity_hours` | liste des heures UTC actives |

---

## NetworkMapper — `network.py`

Graphe relationnel entre sources et entités trouvées.

| Champ | Contenu |
|-------|---------|
| `nodes` | sources + entités uniques |
| `edges` | (source → entité) |
| `triangulations` | entités présentes dans ≥2 sources distinctes |
| `geo_clusters` | groupes par grille 0.05° lat/lon |

---

## HistoricalScraper — `historical.py`

Timeline triée des findings datés.

- Formats acceptés : epoch float, ISO8601, EXIF (`YYYY:MM:DD HH:MM:SS`)
- Comptage des sources `wayback` / `archive`
- Champs : `earliest`, `latest`, `total_events`, `wayback_count`, `events[]`

---

## MetadataExtractor — `metadata.py`

Corrélation des métadonnées fichiers.

| Champ | Source |
|-------|--------|
| `gps_points` | EXIF GPSLatitude/GPSLongitude |
| `devices` | EXIF Make/Model groupés |
| `serial_reuse` | numéros de série présents ≥2 fois |
| `stega_signals` | findings de type `steganography` |

---

## Intégration engine

```python
# engine.py — step 5b
try:
    from agent.osint.analyzers import run_all as _run_all
    report.analyzers = {k: v.to_dict() for k, v in _run_all(findings).items()}
except Exception as _e:
    report.analyzers = {"_error": str(_e)}
```

Les résultats sont inclus dans le rapport HTML via le reporter Jinja2.

## Liens

- [[phase7.6-osint-overview]]
- [[phase7.6-session4-complete]]
- [[phase7.6-persistance-reports]]
