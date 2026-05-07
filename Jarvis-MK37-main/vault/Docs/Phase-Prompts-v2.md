---
title: Phase Prompts — v2 (révisés après audit Phase 6+7)
date: 2026-05-01
tags: [prompts, phases, roadmap, safety]
priority: high
---

# Phase Prompts v2

> Prompts révisés pour les phases 6→11 après audit du code existant.
> Les phases 0, 1, 2, 3, 4, 5, 6, 7 sont **déjà implémentées** (107 tests OK).
> Restent : **8 (perception), 9 (LAM), 10 (auto-évolution), 11 (packaging)**.

---

## État actuel (réf. avant de coder une nouvelle phase)

| Phase | Module | Status | Tests |
|-------|--------|--------|-------|
| 0 | bootstrap, hardware_detect, local_llm_provider | ✅ | 19 |
| 1 | classifier (3 axes) | ✅ | 19 |
| 2 | voices (fast/deep/uncensored) + voice_router + refusal_detector | ✅ | 24 |
| 3 | mission_models + mission_store + mission_runner + voice_mission | ✅ | 19 |
| 4 | working/episodic/semantic/procedural/rag (memory 4 couches) | ✅ | mémoire intégrée |
| 5 | authority parole vs action | ✅ | 9 |
| 6 | ui_wizard.py/html + auto-optimizer | ✅ | 5 |
| 7 | flow_manager + status query + async notif callback | ✅ | 5 |
| 8 | perception screen | ⏳ |
| 9 | LAM control | ⏳ |
| 10 | auto-évolution | ⏳ |
| 11 | packaging .exe | ⏳ |

---

## Gaps trouvés à la review (à corriger AVANT phase 8)

### Phase 6 (wizard) — gaps

1. **Pas de chiffrement des clés API** : `config/api_keys.json` est en clair sur disque.
   → Ajouter option "chiffrer avec mot de passe" via `cryptography.fernet` au step 3.
2. **Pas de skip granulaire** au step 2 si Ollama down. L'user reste bloqué.
   → Bouton "Skip — j'utiliserai cloud only" qui passe au step 3.
3. **Justification du modèle dépend des seuils hardware_detect** : si l'user a un GPU borderline (5 GB), il aura le 3B alors que 14B passerait. Ajouter un switch "qualité préférée vs latence".

### Phase 7 (flow_manager) — gaps

1. **`consume_async_notifications()` n'est jamais appelé dans `main.py`**.
   → La queue se remplit, mais Jarvis n'annonce jamais les missions terminées.
   → Doit être polled depuis le voice loop principal (ex: toutes les 5s entre les tours).
2. **Pas de mutex sur le speech output** : si une mission termine pendant que l'user parle, le TTS peut se chevaucher avec l'écoute mic.
   → Lock `is_user_speaking` à respecter avant tout TTS auto-déclenché.
3. **"Foreground interrupt" ne cancelle pas la mission running** : c'est une vraie fast-lane parallèle (correct), mais à expliciter dans la doc UI sinon malentendu.
4. **`is_status_query` regex naïve** : matche "où en est" mais pas "ça en est où ?". Ajouter un mini-classifieur LLM si dispo.

---

## PROMPT PHASE 8 — Perception & Overlay (révisé)

> ⚠️ Avant tout : ajouter une **safety net** privacy. Sans ça, refuser de coder.

### Pré-requis safety obligatoires

- [ ] Indicator visuel permanent (icône systray rouge clignotante quand perception ON)
- [ ] Hotkey global `Ctrl+Alt+P` qui toggle perception ON/OFF instantanément
- [ ] **Whitelist d'applications** : config `perception.allowed_apps[]` — perception OFF par défaut sur Discord, Slack, banking, password managers, fullscreen apps
- [ ] Mode "OFF par défaut" au premier lancement, opt-in explicit dans le wizard step 5 (à ajouter)

### TÂCHE

Implémenter Vision Continue + UI Contextuelle.

**Fichiers à lire** : `main.py`, `agent/voice_router.py`, `agent/specialists.py`, `agent/awareness.py` (qui existe déjà — capture buffer + hash).

### Spécifications

**1. `agent/perception.py`** — Refonte du awareness existant

```python
class PerceptionEngine:
    def __init__(self,
                 capture_interval_s: float = 5.0,
                 hash_diff_threshold: float = 0.05):
        ...

    def start(self) -> None: ...   # daemon thread
    def stop(self) -> None: ...
    def pause(self) -> None: ...   # via hotkey
    def resume(self) -> None: ...
    def is_active(self) -> bool: ...
    def is_app_allowed(self, app_name: str) -> bool: ...
```

**Hash perceptuel obligatoire** (pas pixel) :
- Utilise `imagehash.phash()` (DCT-based) — robuste aux changements de curseur, animations subtiles
- Compare hash actuel vs précédent, skip si distance Hamming < seuil

**Rate limit** : max 1 capture / 3s, max 200 captures/heure (anti-coûts Gemini).

**Détection de l'app foreground** :
- Windows : `pygetwindow.getActiveWindow().title` + check whitelist
- Si app non-whitelisted → skip ce cycle

**OCR séparé** :
- Tesseract local pour les coords (pas Gemini, qui hallucine sur pixel-perfect)
- Gemini Vision pour la sémantique ("y a-t-il une erreur ?")

**2. `ui/overlay_manager.py`**

```python
class OverlayManager:
    def show_bubble(self, x: int, y: int, text: str, duration_s: float = 5.0): ...
    def hide_all(self): ...
```

PyQt6 `QWidget` avec :
- `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`
- `setAttribute(Qt.WA_TranslucentBackground)`
- Positionnement : `move(x_screen, y_screen)` calé sur coords OCR

**Mode fullscreen detection** : si app fullscreen détectée (ex: jeu) → masquer toutes les overlays.

**3. Lien Voie 1**

Si erreur détectée par perception :
- Crée un `Episode` dans `episodic.py` (`type="discovery"`, `emotional_valence=-0.3`)
- Pousse une notif dans `voice_router._ASYNC_NOTIFICATIONS` du type :
  `"Je vois une erreur à l'écran (X). Veux-tu que je corrige ?"`
- Au prochain `consume_async_notifications()`, Jarvis le dit

### Livrables

- `agent/perception.py` + tests (mock screen capture)
- `ui/overlay_manager.py` + tests (mock PyQt)
- Update `main.py` : démarrage perception après bootstrap si activé dans `runtime.json`
- Update wizard step 5 : opt-in privacy + whitelist apps
- `tests/test_perception.py` : hash diff, app whitelist, rate limit, fullscreen pause

---

## PROMPT PHASE 9 — LAM (révisé en 2 sous-phases)

> ⚠️ La phase LAM peut **casser le PC**. Splitée en 9a (démo) et 9b (actif).
> 9b ne se code QUE si 9a a tourné 1 mois sans incident.

### Pré-requis safety obligatoires

- [ ] **Authority en mode "ask" par défaut sur TOUTES les actions LAM** (pas juste sensibles)
- [ ] **Hotkey global `Ctrl+Alt+Esc`** : kill switch, abort toute action LAM en cours
- [ ] **Rate limit dur** : max 5 actions/seconde, max 100 actions/minute. Au-delà → freeze + alert.
- [ ] **Audit log persistant** dans `memory/lam_audit.log` JSONL (timestamp, action, coords, screenshot_hash_avant, screenshot_hash_après, success)
- [ ] **Rollback** : commande "annule la dernière action" qui :
  - keyboard : Ctrl+Z
  - file : restore depuis trash si supprimé
  - mouse : pas rollbackable, mais alert l'user

### Phase 9a — DEMO MODE (à faire en premier)

**Comportement** : Jarvis dit ce qu'il VA faire, dessine un overlay autour de la cible, **n'agit pas**.

```python
class LAMController:
    def __init__(self, demo_mode: bool = True): ...
    def execute(self, intent: str) -> LAMResult: ...
```

Pipeline démo :
1. Screenshot
2. Vision LLM analyse + retourne JSON `{"action": "click", "target_description": "...", "reason": "..."}`
3. **OCR + UIA pour résoudre les coords** (PAS le LLM)
4. Overlay rouge entoure la cible
5. TTS "je vais cliquer sur 'Envoyer' pour valider le formulaire"
6. **Stop. Pas d'action.**

Live 50 demos validés par l'user → activer 9b.

### Phase 9b — ACTIF (après audit)

Mêmes étapes que 9a + :
4bis. Authority gate (ask par défaut, allow seulement si user a tagué "auto-approve")
5bis. PyAutoGUI execute avec `pyautogui.PAUSE = 0.5` (anti-spam)
6. Self-correction : nouveau screenshot → comparer perceptual hash → vérifier diff attendue
7. Si diff inattendue → rollback + log + alert user

**Ne JAMAIS retry plus de 2 fois.**

**Préfère UIA over Vision** :
- `uiautomation` (Windows) → trouve l'élément par accessibility tree, click précis
- Vision = fallback seulement si UIA ne trouve rien
- 95% des UIs modernes ont UIA fiable

### Livrables

- `agent/lam_controller.py` (mode demo + actif via flag)
- `agent/lam_resolver.py` (UIA → OCR → Vision en cascade)
- Update `agent/authority.py` : ajouter `lam_action` comme catégorie `ask_for` par défaut
- Hotkey listener `agent/emergency_stop.py`
- `tests/test_lam.py` : mock screenshot + UIA, vérifie rate limit, kill switch, rollback

---

## PROMPT PHASE 10 — Auto-Évolution (révisée — réduite)

> 🛑 La version originale était dangereuse (auto-install + auto-import = RCE).
> Version réduite : **Suggestion + Review user**, jamais d'auto-import.

### Pré-requis safety obligatoires

- [ ] **JAMAIS de subprocess install sans confirmation user explicite**
- [ ] **Sandbox réelle** pour le test : venv isolé OU container Docker, pas un `subprocess.run()` direct
- [ ] **Whitelist d'origines** : seulement PyPI officiel, pas un wget arbitraire
- [ ] Specialist auto-codé écrit dans `agent/specialists/_drafts/` (pas chargé tant que pas validé)
- [ ] Git commit auto pour chaque draft → l'user peut review/rollback

### TÂCHE

**Phase 10a — Détection + Suggestion** (à faire d'abord)

`agent/evolution_engine.py` :

```python
class EvolutionEngine:
    def detect_gap(self, query: str, voice2_response: VoiceResponse) -> Optional[Gap]:
        """Si réponse Voie 2 trop courte ou contient 'I don't know how' → gap."""

    def propose_specialist(self, gap: Gap) -> SpecialistDraft:
        """Web search via specialist research → identifie tool manquant.
        Génère un draft de specialist + tests."""

    def install_draft(self, draft: SpecialistDraft) -> str:
        """Écrit le code dans agent/specialists/_drafts/<name>.py.
        Git commit auto. Ne charge PAS dans SPECIALISTS."""
```

Ce que Jarvis dit à l'user :
> "J'ai vu que je manquais d'un specialist pour [X]. J'ai écrit un brouillon dans
> `agent/specialists/_drafts/specialist_x.py`. Tu peux le review et l'activer
> avec `/activate_specialist x`."

**Phase 10b — Activation manuelle** (par commande explicite)

```python
def activate_specialist(name: str) -> None:
    """Move _drafts/<name>.py → specialists/<name>.py.
    Run tests sandbox. Si OK → register dans SPECIALISTS via importlib."""
```

**Phase 10c — Auto-install software** : SKIP. Trop dangereux. Si l'user veut un nouveau soft, il l'installe lui-même.

### Livrables

- `agent/evolution_engine.py`
- `agent/specialists/_drafts/` (gitignored sauf `__init__.py`)
- Commande UI/voix `/activate_specialist <name>`
- `tests/test_evolution.py`

---

## PROMPT PHASE 11 — Packaging .exe (révisé)

### Pré-requis

- [ ] **Estimer la taille** du bundle avant de commencer (probablement 800 Mo - 2 Go)
- [ ] **Plan code signing** : décision certificate auto-signé OU EV cert ($300/an) OU Microsoft Store (gratuit mais review)
- [ ] **Plan auto-update** : Sparkle, ou check version au boot vers `github.com/.../releases/latest`

### TÂCHE

**1. `build_exe.py`** — PyInstaller

```python
PYINSTALLER_ARGS = [
    "main.py",
    "--name=Jarvis-MK37",
    "--windowed",
    "--icon=face.png",
    "--add-data=ui.html;.",
    "--add-data=ui_wizard.html;.",
    "--add-data=face.png;.",
    "--add-data=core/prompt.txt;core",
    "--add-data=config/authority.json;config",
    "--add-data=config/personality.yaml;config",
    "--add-data=config/api_keys.example.json;config",
    "--collect-all=torch",
    "--collect-all=transformers",
    "--collect-all=sentence_transformers",
    "--collect-all=PyQt6",
    "--collect-all=webview",
    "--hidden-import=anthropic",
    "--hidden-import=google.genai",
    "--hidden-import=imagehash",
    "--noconfirm",
    "--clean",
]
```

**Test obligatoire** : run sur **VM Windows fresh sans Python**.

**2. Bootstrapper `installer/bootstrap.exe`** (lancé avant `Jarvis-MK37.exe`)

Pseudocode :
```
if not exists("C:/Users/<user>/AppData/Local/Programs/Ollama/ollama.exe"):
    if user_confirms("Ollama est requis. Installer maintenant ?"):
        download(OLLAMA_INSTALLER_URL)
        run_with_admin(ollama_installer)
exec(jarvis-mk37.exe)
```

⚠️ **Ne JAMAIS install Ollama silently sans confirmation** (politique Microsoft).

**3. Inno Setup `installer/setup.iss`**

```iss
[Setup]
AppName=Jarvis MK37
AppVersion=0.1.0
DefaultDirName={pf}\JarvisMK37
DefaultGroupName=Jarvis MK37
OutputBaseFilename=Jarvis-MK37-Setup
Compression=lzma
SolidCompression=yes
SignTool=signtool sign /f mycert.pfx /p $q$q $f

[Files]
Source: "dist\Jarvis-MK37\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Jarvis MK37"; Filename: "{app}\Jarvis-MK37.exe"
Name: "{userdesktop}\Jarvis MK37"; Filename: "{app}\Jarvis-MK37.exe"

[Run]
Filename: "{app}\bootstrap.exe"; Description: "Setup runtime"; Flags: postinstall

[Dirs]
Name: "{userappdata}\JarvisMK37"; Permissions: users-full
```

**4. CI GitHub Actions**

`.github/workflows/build.yml` qui build sur `windows-latest` à chaque tag, upload dans Releases.

### Livrables

- `build_exe.py`
- `installer/setup.iss`
- `installer/bootstrap.exe` (Go ou Rust pour bootstrapper léger)
- `.github/workflows/build.yml`
- Doc `BUILD.md` avec étapes manuelles (signtool, etc.)

### Risques anticipés

| Risque | Mitigation |
|--------|------------|
| Bundle > 1.5 GB | Activer `--exclude-module` sur `tkinter`, `matplotlib`, etc. inutiles |
| Hidden imports torch | Tester sur VM, ajouter au fur et à mesure |
| Antivirus false positive | Soumettre à VirusTotal avant release, demander whitelisting |
| SmartScreen block | Code signing OBLIGATOIRE pour distribution publique |
| Ollama install échoué | Bootstrapper donne un lien manuel + retry |

---

## Méta : ce qui doit être ajouté AVANT phase 8

1. **Fix gap phase 7** : appeler `consume_async_notifications()` dans le voice loop de `main.py` (1 ligne ajoutée toutes les 5s).
2. **Fix gap phase 6** : ajouter chiffrement clés en option dans le wizard.
3. **Phase 7.5 — Safety Net** :
   - Hotkey global `Ctrl+Alt+Esc`
   - Mode "demo only" toggleable depuis l'UI
   - Audit log persistant (`memory/safety_audit.log`)
   - Bouton "rollback dernière action"

Sans cette safety net, ne pas commencer phases 8/9/10.


## Liens Transverses
- [[09-Specialists/specialist-researcher.md]]
- [[14-Phases/phase7-audit.md]]
