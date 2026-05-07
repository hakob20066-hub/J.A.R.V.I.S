---
title: Phase 7.6 — Session 6 ✅ DONE (Wizard + osint_lookup + Authority + Tests intégration)
date: 2026-05-07
tags: [phase7.6, osint, session6, livraison, done, wizard, action, authority]
parent_moc: [[00-MOC/MOC-OSINT]]
---

# Session 6 — Wizard step 4.6 + Action osint_lookup + Tests intégration

**Statut** : ✅ DONE  
**Tests** : **330/330 PASS** (304 base + 26 Session 6)  
**Phase 7.6** : **COMPLÈTE** (sessions 1-6)

---

## Livré Session 6

### `agent/osint/wizard.py` — OSINTWizard

Setup obligatoire step 4.6. Gère :
- `is_complete()` — lit `config/osint_wizard_done.json`
- `save_identities(dict)` — écrit `config/osint_self_identities.json` + marque done
- `auto_init()` — init silencieux avec identités vides (premier boot)
- `get_identities()` — lecture des self_identities
- `generate_consent_id(target_raw)` — délègue à `LegalGuard.record_consent()`
- `setup_summary()` — résumé lisible de l'état courant
- `disclaimer_text()` — texte légal RGPD/CCPA pour popup externe

```python
from agent.osint.wizard import get_wizard
w = get_wizard()
w.save_identities({"name": "Jean", "emails": ["jean@x.com"], "handles": ["jeand"]})
consent_id = w.generate_consent_id("target@external.com")
```

### `actions/osint_lookup.py` — Action unifiée

Point d'entrée JARVIS pour tous les lookups OSINT. Intègre :
1. Parse target depuis `parameters` (clés: `target`, `email`, `domain`, `ip`, `username`)
2. Auto-init wizard si non configuré
3. Bloc consentement si `mode=external_target` sans `consent=True`
4. Appel `OSINTEngine.lookup()`
5. Formatage rapport texte lisible (top 5 findings, types, sources, chemin HTML)

```python
# Depuis agent_dispatcher
result = osint_lookup({
    "target": "example.com",
    "mode": "self_audit",
    "depth": 2,
})
# → "=== OSINT — example.com (domain) ===\n3 finding(s) | ..."
```

### `config/authority.json`

Ajout dans `ask_for` :
```json
"osint_lookup:external_target"
```
→ L'Authority Engine demande confirmation avant tout lookup sur une cible externe.

---

## Tests Session 6 (26 dans `tests/test_session6_osint.py`)

### A) OSINTWizard (10)
- `test_not_complete_by_default` — wizard vierge = False
- `test_complete_after_save` — save_identities → True
- `test_save_writes_identities_file` — contenu JSON vérifié
- `test_get_identities_empty_before_setup` — dict vide si pas de fichier
- `test_get_identities_after_save` — lecture correcte
- `test_auto_init_marks_complete` — auto_init sans setup préalable
- `test_auto_init_idempotent` — ne reset pas identités existantes
- `test_setup_summary_not_complete` — message "non configuré"
- `test_setup_summary_complete` — nom + email dans résumé
- `test_disclaimer_text_contains_rgpd` — RGPD + limite 5/jour

### B) osint_lookup action (8)
- `test_no_target_returns_help` — message d'aide si target vide
- `test_external_without_consent_shows_disclaimer` — disclaimer + "consent=True"
- `test_self_audit_calls_engine` — moteur appelé + "example.com" dans résultat
- `test_engine_error_returns_message` — exception engine → message erreur
- `test_report_error_shown` — `report.error` dans output
- `test_report_cancelled_shown` — "CANCELLED" dans output
- `test_findings_formatted` — type + source présents dans sortie
- `test_external_with_consent_calls_engine` — consent_id transmis au moteur

### C) Authority (2)
- `test_osint_lookup_in_ask_for` — présent dans authority.json
- `test_self_audit_not_blocked` — pas dans denylist

### D) Pipeline intégration (6)
- `test_email_self_audit_full_pipeline` — email → 1 finding breach
- `test_domain_with_findings` — domain → 2 findings, source enregistrée
- `test_connector_failure_recorded` — failure → sources_failed
- `test_analyzers_populated` — report.analyzers dict présent
- `test_report_has_timing` — duration_ms > 0
- `test_cancel_flag_stops_pipeline` — cancel() → report.cancelled = True

---

## État final Phase 7.6

| Composant | Module | Statut |
|-----------|--------|--------|
| Engine + Target + Pivot + Scheduler | `agent/osint/` | ✅ S1 |
| KaliRunner + Safety + Audit + UIBridge | `agent/osint/` | ✅ S1 |
| 20 wrappers Kali core | `connectors/kali/` | ✅ S2 |
| SpiderFoot + recon-ng + 15 wrappers Kali | `agent/osint/` | ✅ S3 |
| 4 analyzers + base HTTP + 11 connecteurs Python | `connectors/python/` | ✅ S4 |
| 15 connecteurs Python + Reporter HTML | `connectors/python/` + `reporter.py` | ✅ S5 |
| Wizard + Action osint_lookup + Authority | `wizard.py` + `actions/` | ✅ S6 |
| **Tests totaux** | `tests/` | **330/330** |

---

## Liens

- [[phase7.6-session5-complete]]
- [[phase7.6-wizard-step-4.6]]
- [[phase7.6-safety-legal-guard]]
- [[phase7.6-livraison-6-sessions]]
- [[00-MOC/MOC-OSINT]]
