"""
Phase 7.6 OSINT v3.3 « Kali Hybrid » — enregistrement architecture (~24 notes).
Lancer une fois : `python _gen_phase76_osint.py`
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATE = "2026-05-05"


def w(rel: str, fm: dict, body: str):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    p.write_text("\n".join(lines) + "\n\n" + body.strip() + "\n", encoding="utf-8")


def note(folder: str, name: str, title: str, tags: list, body: str,
         links: list = None, moc: str = None, code: str = None):
    fm = {"title": title, "date": DATE, "tags": tags}
    if code:
        fm["linked_code"] = code
    if moc:
        fm["parent_moc"] = f"[[00-MOC/{moc}]]"
    rel = ""
    if links:
        rel = "\n\n## Liens\n" + "\n".join(f"- [[{l}]]" for l in links)
    w(f"{folder}/{name}.md", fm, body + rel)


# ============================================================
# 14-Phases : architecture Phase 7.6
# ============================================================
P = "14-Phases"
M = "MOC-Phases"

note(P, "phase7.6-osint-overview",
    "Phase 7.6 — OSINT (Kali Hybrid) — Overview",
    ["phase7.6", "osint", "kali", "architecture"],
    "Phase intercalée entre 7.5 (Safety Net) et 8 (Perception). Moteur OSINT unifié multi-sources avec "
    "**Kali Linux en backend prioritaire** (WSL/native/docker), **fallback Python** si Kali absent.\n\n"
    "**Capacités** : 12 types de cibles, 60+ wrappers Kali, 25 connecteurs Python fallback, "
    "300+ sources via SpiderFoot+recon-ng, 4 analyseurs comportementaux, export Maltego .mtgx, "
    "UI dédiée (panel gauche on-demand + fenêtre rapport Cytoscape), persistance complète indexée.",
    ["phase7.6-objectif", "phase7.6-kali-runner", "phase7.6-targets-12",
     "phase7.6-livraison-6-sessions"], moc=M)

note(P, "phase7.6-objectif",
    "Phase 7.6 — Objectif & motivation",
    ["phase7.6", "objectif"],
    "**Pourquoi Kali Hybrid plutôt que Python pur** : Kali maintient déjà 600+ outils OSINT "
    "(sherlock, maigret, theHarvester, recon-ng, SpiderFoot, exiftool, stegseek, etc.). Re-coder en "
    "Python = ~14k lignes vs ~5.5k en wrappers Kali, et Kali reste à jour.\n\n"
    "**Réduction code 65%, sources OSINT effectives ×3** (300+ via méta-frameworks). "
    "Maintenance long-terme : Kali team le fait.",
    ["phase7.6-osint-overview", "phase7.6-kali-runner",
     "01-Concepts/concept-kali-wsl", "01-Concepts/concept-spiderfoot"], moc=M)

note(P, "phase7.6-targets-12",
    "Phase 7.6 — 12 types de cibles auto-détectés",
    ["phase7.6", "target", "normalizer"],
    "`TargetNormalizer.detect(raw)` → type ∈ {email, domain, ip, username, instagram_handle, "
    "social_handle, person_full, address, phone, crypto, image, pseudonym}.\n\n"
    "Chaque type déclenche un set spécifique de connecteurs via `SourceDispatcher.select(type)`. "
    "Cibles ambiguës (ex: 'fatih' = nom OU username) → demande clarification user.",
    ["phase7.6-pivot-cascade", "phase7.6-osint-overview"], moc=M)

note(P, "phase7.6-pivot-cascade",
    "Phase 7.6 — Auto-pivot cascade (depth 2 default, max 3)",
    ["phase7.6", "pivot", "cascade"],
    "Chaque finding pivotable → nouvelle Target ajoutée à la queue active. Streaming continu, "
    "pas de phases discrètes.\n\n"
    "**Exemple** : `@fatihmakes` → Sherlock trouve GitHub → email du profil GitHub → HIBP leaks → ...\n\n"
    "**Garde-fous** : `max_total_targets=500`, `max_runtime=600s`, `max_depth=3`, kill switch "
    "Phase 7.5 (`Ctrl+Alt+Esc`).",
    ["phase7.6-scheduler-adaptive", "phase7.6-targets-12", "01-Concepts/concept-osint-pivot"], moc=M)

note(P, "phase7.6-scheduler-adaptive",
    "Phase 7.6 — AdaptiveScheduler (pool dynamique)",
    ["phase7.6", "scheduler", "perf"],
    "Pool de workers asyncio dont taille s'ajuste en continu :\n"
    "- min=2, max_cap=20\n"
    "- réduit si CPU>80% ou RAM dispo<1GB pendant 5s\n"
    "- augmente si CPU<50% et queue>pool_size\n\n"
    "Évite à la fois la lenteur (parallélisation maxi) et le freeze système.",
    ["phase7.6-pivot-cascade"], moc=M)

note(P, "phase7.6-kali-runner",
    "Phase 7.6 — KaliRunner (détection backend)",
    ["phase7.6", "kali", "wsl"],
    "Détecte au boot le meilleur backend Kali :\n"
    "1. WSL Kali (`wsl -d kali-linux -- which sherlock`) — **prioritaire**\n"
    "2. WSL Ubuntu + apt-installed tools\n"
    "3. Native Linux\n4. Docker `kalilinux/kali-rolling`\n5. Aucun → fallback Python\n\n"
    "**Si WSL absent au boot** : popup user 'Installer WSL+Kali ?' (lock décision Phase 7.6).\n\n"
    "API : `is_tool_available(name)`, `run(cmd, timeout, json_output)`, `install_tool(pkg)`.",
    ["phase7.6-spiderfoot-client", "phase7.6-wizard-step-4.6", "01-Concepts/concept-kali-wsl"],
    moc=M, code="agent/osint/kali_runner.py")

note(P, "phase7.6-spiderfoot-client",
    "Phase 7.6 — SpiderFoot client (200 modules d'un coup)",
    ["phase7.6", "spiderfoot", "kali"],
    "SpiderFoot lancé en daemon (`spiderfoot -l 127.0.0.1:5001`) **à la demande au 1er OSINT** — "
    "PAS auto au boot Jarvis, économise ~500MB RAM si OSINT pas utilisé.\n\n"
    "Wrapper REST API : `POST /startscan`, poll `/scanstatus/{id}`, `GET /scaneventresults/{id}`.\n\n"
    "**1 client = 200 sources OSINT**.",
    ["phase7.6-kali-runner", "phase7.6-reconng-client", "01-Concepts/concept-spiderfoot"], moc=M)

note(P, "phase7.6-reconng-client",
    "Phase 7.6 — recon-ng client (100+ modules)",
    ["phase7.6", "reconng", "kali"],
    "Recon-ng accédé via CLI dans workspaces dédiés Jarvis. 100+ modules emails/hosts/profils. "
    "Init workspace par cible : `recon-ng -w jarvis_<target_hash> -r script.rc`.\n\n"
    "Plus complexe que SpiderFoot mais offre des modules uniques (hibp_breach, github_dorks, builtwith).",
    ["phase7.6-spiderfoot-client", "phase7.6-kali-runner"], moc=M)

note(P, "phase7.6-connectors-kali",
    "Phase 7.6 — 60 wrappers Kali (~50 lignes chacun)",
    ["phase7.6", "connectors", "kali"],
    "Wrappers thin autour des CLI Kali. Privilégier outils avec `--json` (sherlock, theharvester, etc.).\n\n"
    "**Liste** : sherlock, maigret, holehe, theHarvester, sublist3r, subfinder, amass, dnsenum, "
    "dnsrecon, dig, whois, host, nmap, shodan-cli, waybackurls, gau, gitleaks, trufflehog, "
    "exiftool, stegseek, zsteg, steghide, photon, googler, linkedin2username, instaloader, "
    "osintgram, phoneinfoga, twint, nuclei, ffuf, gobuster, dirsearch, fierce, ... (60 total).",
    ["phase7.6-kali-runner", "phase7.6-connectors-python"], moc=M)

note(P, "phase7.6-connectors-python",
    "Phase 7.6 — 25 connecteurs Python fallback / non-Kali",
    ["phase7.6", "connectors", "python"],
    "Sources qui n'existent pas en Kali ou nécessitent API key cloud :\n"
    "HIBP, PimEyes, FaceCheck.ID, Pages Blanches FR, IDCrawl, BeenVerified, Hunter.io, EmailRep, "
    "Shodan API, IPinfo, GreyNoise, AbuseIPDB, Cadastre.data.gouv.fr, Nominatim, BlockchainInfo, "
    "Etherscan, OXT, GraphSense, TinEye, Yandex reverse, Wigle, ... (25 total).",
    ["phase7.6-connectors-kali"], moc=M)

note(P, "phase7.6-analyzers",
    "Phase 7.6 — 4 analyseurs cross-cutting",
    ["phase7.6", "analyzers", "behavior"],
    "**BehaviorAnalyzer** : timezone (pic posts), langue, cadence, sentiment, topics (BERTopic).\n"
    "**NetworkMapper** : co-followers, co-mentions, geo-clusters, triangulation identité.\n"
    "**HistoricalScraper** : Wayback, archive.today, Google cache, Pushshift Reddit.\n"
    "**MetadataExtractor** : EXIF (GPS, device), stéganalyse LSB, PDF/Office metadata, video codec.",
    ["phase7.6-osint-overview"], moc=M)

note(P, "phase7.6-maltego-export",
    "Phase 7.6 — Export Maltego natif (.mtgx + .csv)",
    ["phase7.6", "maltego", "export"],
    "`MaltegoExporter` génère `.mtgx` (XML graphe importable Maltego CE/Pro) et `.csv` fallback.\n\n"
    "**Mapping entités** : Person, EmailAddress, Phone, Domain, IPv4Address, Alias, "
    "affiliation.{Twitter,Instagram,LinkedIn}, Location (lat/lon), Image, Hash, BitcoinAddress.\n\n"
    "**Auto-open** (lock décision) : Jarvis lance `maltego <path>.mtgx` après export → fenêtre "
    "Maltego s'ouvre avec graphe pré-chargé.",
    ["phase7.6-ui-report-window", "01-Concepts/concept-maltego-mtgx"], moc=M)

note(P, "phase7.6-ui-panel-gauche",
    "Phase 7.6 — UI panel OSINT (gauche, on-demand)",
    ["phase7.6", "ui", "panel"],
    "Panneau latéral **gauche** dans `ui.html`, **collapsé par défaut**, s'ouvre **uniquement** "
    "quand tool `osint_lookup` est appelé (lock décision).\n\n"
    "**Contenu** : target + mode badge, progress bar live, findings streamés (slide-in), boutons "
    "'Open Full Report' + 'Cancel'.\n\n"
    "**Drag-drop image** activé sur le panel (priorité 1).\n\n"
    "Bridge Python ↔ JS : `_OSINTApi` class dans `ui.py`.",
    ["phase7.6-ui-report-window", "phase7.6-drag-drop-image"], moc=M)

note(P, "phase7.6-ui-report-window",
    "Phase 7.6 — Fenêtre rapport (Cytoscape cyberpunk)",
    ["phase7.6", "ui", "report", "cytoscape"],
    "`osint_report.html` — pywebview window séparée, standalone (libs JS embarquées offline).\n\n"
    "**Tabs** : Overview / Findings / Graph / Timeline / Behavior / Raw / Export.\n\n"
    "**Graph Cytoscape.js** : layout cose-bilkent force-directed, glow cyberpunk, node shapes "
    "par type entité (round=person, hex=domain, diamond=leak), edge gradients, tooltips Tippy.js, "
    "right-click context menu (Pivot/Hide/Highlight cluster).\n\n"
    "Plugins : cose-bilkent, popper+tippy, context-menus, edgehandles.",
    ["phase7.6-ui-panel-gauche", "phase7.6-maltego-export"], moc=M)

note(P, "phase7.6-drag-drop-image",
    "Phase 7.6 — Drag-drop image dans panel (P1)",
    ["phase7.6", "ui", "drag-drop", "image"],
    "Drop image sur le panel OSINT → Jarvis lance auto-OSINT type=image (cascade reverse search "
    "+ EXIF + stéganalyse + face recognition si keys présentes).\n\n"
    "Pipeline JS → `osint_save_dropped_image(filename, b64)` → `osint_lookup_image(path)` → "
    "engine déclenche cascade type=image.",
    ["phase7.6-ui-panel-gauche"], moc=M)

note(P, "phase7.6-safety-legal-guard",
    "Phase 7.6 — LegalGuard (self_audit vs external_target)",
    ["phase7.6", "safety", "legal", "rgpd"],
    "**Mode `self_audit`** : handles déclarés au wizard step 4.6 → autoallow.\n"
    "**Mode `external_target`** : disclaimer popup obligatoire au 1er usage (RGPD/CCPA), "
    "consentement loggé HMAC, rate limit dur **5 lookups MAX-mode/jour**.\n\n"
    "Cibles `image` face recognition + `address` voisinage social = **refus par défaut** sauf "
    "override explicite. Authority `osint_lookup:external_target:maximum` permanent dans `ask_for`.",
    ["phase7.6-audit-log-hmac", "phase7.6-wizard-step-4.6"], moc=M)

note(P, "phase7.6-audit-log-hmac",
    "Phase 7.6 — Audit log signé HMAC",
    ["phase7.6", "audit", "hmac", "security"],
    "`memory/osint_audit.log` JSONL append-only, **chaque entry signée HMAC-SHA256** :\n"
    "```jsonl\n{\"ts\":..., \"target_hash\":\"sha256:...\", \"mode\":\"external_target\", "
    "\"depth\":3, \"sources\":[...], \"consent\":\"popup_v1_2026-05-05\", \"hmac\":\"...\"}\n```\n\n"
    "Hashing target sensible (jamais en clair). Rotation par taille (10MB).",
    ["phase7.6-safety-legal-guard"], moc=M)

note(P, "phase7.6-persistance-reports",
    "Phase 7.6 — Persistance reports (tout gardé, indexé)",
    ["phase7.6", "persistance", "reports", "sqlite"],
    "**Tous rapports conservés** indéfiniment (lock décision) dans "
    "`memory/osint_reports/<target_hash>__<iso_ts>/` :\n"
    "- report.json + report.html (viewer) + report.mtgx + report.csv + report.md\n"
    "- findings.jsonl + images/ EXIF stripped\n\n"
    "**Index SQLite** `_index.db` searchable par target_hash, type, mode, date, sources.\n"
    "Onglet '📂 Past Reports' dans le panel pour navigation/recherche.",
    ["phase7.6-osint-overview"], moc=M)

note(P, "phase7.6-wizard-step-4.6",
    "Phase 7.6 — Wizard step 4.6 (OBLIGATOIRE)",
    ["phase7.6", "wizard", "setup"],
    "**Step obligatoire au 1er boot** (lock décision user). Affiche :\n"
    "1. Détection backend Kali (WSL/native/docker/none)\n"
    "2. Si none → propose installer WSL+Kali (prompt user, pas silencieux)\n"
    "3. Liste outils détectés vs manquants → bouton 'Install missing (apt)'\n"
    "4. Form `self_identities` (name, emails, handles, phones, addresses) — tous optionnels\n"
    "5. Disclaimer légal RGPD/CCPA obligatoire à signer\n\n"
    "Sans step 4.6 complétée → `osint_lookup` désactivé au runtime.",
    ["phase7.6-kali-runner", "phase7.6-safety-legal-guard"], moc=M)

note(P, "phase7.6-livraison-6-sessions",
    "Phase 7.6 — Plan livraison (6 sessions)",
    ["phase7.6", "roadmap", "sessions"],
    "| Session | Contenu |\n|---|---|\n"
    "| 1 | engine + target + pivot + scheduler + kali_runner + safety + audit + ui_bridge + "
    "panel HTML gauche + drag-drop |\n"
    "| 2 | 20 wrappers Kali core (sherlock/maigret/holehe/theHarvester/...) |\n"
    "| 3 | spiderfoot_client + reconng_client + 15 wrappers Kali restants |\n"
    "| 4 | 25 connecteurs Python fallback + 4 analyzers |\n"
    "| 5 | maltego export + KG persist + reporter HTML + osint_report.html viewer Cytoscape |\n"
    "| 6 | wizard step 4.6 + tool declaration + finitions UI + tests integration + vault notes |\n\n"
    "**Total** : ~5500 lignes code, ~120 tests, 60 wrappers + 25 Python fallback.",
    ["phase7.6-osint-overview"], moc=M)

# ============================================================
# 01-Concepts : concepts liés OSINT
# ============================================================
C = "01-Concepts"
MC = "MOC-Concepts"

note(C, "concept-osint-pivot",
    "Concept — OSINT auto-pivot",
    ["concept", "osint", "pivot"],
    "Cascade d'enrichissement : chaque finding pivotable devient nouvelle Target ajoutée à la "
    "queue active. Streaming continu, pas de phases discrètes.\n\n"
    "Différence vs simple lookup : c'est ce qui transforme un outil en **moteur OSINT** réel "
    "(comme Maltego transforms ou SpiderFoot).",
    ["14-Phases/phase7.6-pivot-cascade", "14-Phases/phase7.6-targets-12"], moc=MC)

note(C, "concept-kali-wsl",
    "Concept — Kali Linux via WSL",
    ["concept", "kali", "wsl", "windows"],
    "Windows Subsystem for Linux (WSL2) permet de faire tourner Kali natif sur Windows. "
    "Détection : `wsl -d kali-linux -- which <tool>`.\n\n"
    "**Avantages** : 600+ outils Kali, apt update, pas de re-implémentation Python.\n"
    "**Latence** : cold-start ~500ms par commande → atténuée par pool subprocess persistants.\n"
    "**Coût RAM** : WSL2 ~1-2GB en idle.",
    ["14-Phases/phase7.6-kali-runner", "concept-spiderfoot"], moc=MC)

note(C, "concept-spiderfoot",
    "Concept — SpiderFoot",
    ["concept", "spiderfoot", "osint"],
    "Méta-framework OSINT avec **200+ modules** intégrés (emails, leaks, dark web, social, "
    "DNS, géolocalisation). Lance en daemon REST (`spiderfoot -l 127.0.0.1:5001`).\n\n"
    "**Pour Jarvis** : 1 wrapper REST = 200 sources d'un coup. Lancé **à la demande** au 1er "
    "OSINT (lock décision — pas auto au boot, RAM-conscious).",
    ["14-Phases/phase7.6-spiderfoot-client"], moc=MC)

note(C, "concept-maltego-mtgx",
    "Concept — Maltego .mtgx (XML graphe)",
    ["concept", "maltego", "mtgx", "graph"],
    "Format XML natif Maltego (`.mtgx`). Importable direct dans Maltego CE/Pro pour analyse "
    "graphique avancée.\n\n"
    "Structure : `<MaltegoMessage>` → `<Entities>` (nodes typés Maltego) + `<Links>` (edges "
    "avec weight et label).\n\n"
    "Jarvis génère .mtgx + lance `maltego <file>.mtgx` (lock décision auto-open) → Maltego "
    "s'ouvre avec graphe pré-chargé.",
    ["14-Phases/phase7.6-maltego-export"], moc=MC)

# ============================================================
# 00-MOC : hub OSINT
# ============================================================
note("00-MOC", "MOC-OSINT",
    "MOC — OSINT (Phase 7.6)",
    ["moc", "osint", "phase7.6", "hub"],
    "Hub OSINT. Phase 7.6 « Kali Hybrid ».\n\n"
    "## Architecture\n"
    "- [[14-Phases/phase7.6-osint-overview]]\n"
    "- [[14-Phases/phase7.6-objectif]]\n"
    "- [[14-Phases/phase7.6-targets-12]]\n"
    "- [[14-Phases/phase7.6-pivot-cascade]]\n"
    "- [[14-Phases/phase7.6-scheduler-adaptive]]\n\n"
    "## Backend Kali\n"
    "- [[14-Phases/phase7.6-kali-runner]]\n"
    "- [[14-Phases/phase7.6-spiderfoot-client]]\n"
    "- [[14-Phases/phase7.6-reconng-client]]\n"
    "- [[14-Phases/phase7.6-connectors-kali]]\n"
    "- [[14-Phases/phase7.6-connectors-python]]\n\n"
    "## Analyse & Export\n"
    "- [[14-Phases/phase7.6-analyzers]]\n"
    "- [[14-Phases/phase7.6-maltego-export]]\n\n"
    "## UI\n"
    "- [[14-Phases/phase7.6-ui-panel-gauche]]\n"
    "- [[14-Phases/phase7.6-ui-report-window]]\n"
    "- [[14-Phases/phase7.6-drag-drop-image]]\n\n"
    "## Sécurité\n"
    "- [[14-Phases/phase7.6-safety-legal-guard]]\n"
    "- [[14-Phases/phase7.6-audit-log-hmac]]\n"
    "- [[14-Phases/phase7.6-persistance-reports]]\n"
    "- [[14-Phases/phase7.6-wizard-step-4.6]]\n\n"
    "## Roadmap\n"
    "- [[14-Phases/phase7.6-livraison-6-sessions]]\n\n"
    "## Concepts liés\n"
    "- [[01-Concepts/concept-osint-pivot]]\n"
    "- [[01-Concepts/concept-kali-wsl]]\n"
    "- [[01-Concepts/concept-spiderfoot]]\n"
    "- [[01-Concepts/concept-maltego-mtgx]]",
    ["INDEX_MAITRE", "00-MOC/MOC-Phases", "00-MOC/MOC-Securite"])


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[OK] Phase 7.6 OSINT v3.3 — 25 notes architecture enregistrees.")
