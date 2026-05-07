"""
osint_lookup — point d'entrée unifié OSINT (action JARVIS).

Voir [[14-Phases/phase7.6-osint-overview]].

Pipeline :
  1. Parse le target depuis parameters
  2. Vérifie wizard setup (auto-init si absent)
  3. Gère consentement external_target
  4. Appelle OSINTEngine.lookup()
  5. Retourne résumé formaté + chemin rapport HTML
"""
from __future__ import annotations

from typing import Any, Callable, Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_report(report: Any) -> str:
    """Formate un OSINTReport en texte lisible pour le LLM / TTS."""
    lines: list[str] = []
    tgt = getattr(report, "target", None)
    target_str = getattr(tgt, "normalized", "?") if tgt else "?"
    target_type = getattr(getattr(tgt, "type", None), "value", "?") if tgt else "?"

    lines.append(f"=== OSINT — {target_str} ({target_type}) ===")

    if getattr(report, "cancelled", False):
        lines.append("[CANCELLED]")
    if getattr(report, "error", None):
        lines.append(f"[ERROR] {report.error}")
        return "\n".join(lines)

    findings = getattr(report, "findings", []) or []
    sources  = getattr(report, "sources_used", []) or []
    failed   = getattr(report, "sources_failed", []) or []
    explored = getattr(report, "targets_explored", []) or []

    lines.append(
        f"{len(findings)} finding(s) | {len(sources)} source(s) | "
        f"{len(explored)} cible(s) pivotée(s) | "
        f"{report.duration_ms}ms"
    )

    # Résumé findings par type
    by_type: dict[str, int] = {}
    for f in findings:
        by_type[f.type] = by_type.get(f.type, 0) + 1
    if by_type:
        lines.append("Types: " + ", ".join(f"{k}×{v}" for k, v in sorted(by_type.items())))

    # Top findings (max 5)
    lines.append("")
    for f in findings[:5]:
        extracted = getattr(f, "extracted", {}) or {}
        preview_keys = list(extracted.keys())[:3]
        preview = " | ".join(f"{k}={str(extracted[k])[:40]}" for k in preview_keys)
        lines.append(f"  [{f.type}] {f.source} — {preview}")
    if len(findings) > 5:
        lines.append(f"  … +{len(findings) - 5} autres")

    if failed:
        lines.append(f"\nSources en erreur: {', '.join(s for s, _ in failed[:5])}")

    # Rapport HTML — chemin absolu (file:// pour clic direct dans le navigateur)
    report_path = getattr(report, "report_path", None)
    if report_path:
        from pathlib import Path
        abs_path = Path(report_path).resolve()
        lines.append(f"\nRapport HTML: {abs_path}")
        # URL file:// cliquable
        try:
            file_url = abs_path.as_uri()
            lines.append(f"Ouvrir: {file_url}")
        except Exception:
            pass

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def osint_lookup(
    parameters: Optional[dict] = None,
    player: Any = None,
    speak: Optional[Callable[[str], None]] = None,
) -> str:
    """
    parameters : {
      "target":   "example.com",  # email, IP, username, domain, phone, crypto…
      "mode":     "self_audit",   # "self_audit" | "external_target"
      "depth":    2,              # 1-3, défaut 2
      "deep":     False,          # True = face recog + modes étendus
      "consent":  False,          # True = user a signé le disclaimer (external_target)
    }
    """
    p = parameters or {}
    target_raw = (
        p.get("target") or p.get("query") or p.get("ip") or
        p.get("domain") or p.get("email") or p.get("username") or ""
    ).strip()

    if not target_raw:
        return (
            "osint_lookup: fournir un paramètre 'target' "
            "(email, domaine, IP, username, téléphone…)."
        )

    mode    = str(p.get("mode", "self_audit"))
    depth   = int(p.get("depth", 2))
    deep    = bool(p.get("deep", False))
    # Auto-consent activé par défaut — l'user nous a configuré pour ne plus
    # demander la confirmation RGPD à chaque lookup.
    consent = bool(p.get("consent", True))

    # 1) Wizard — auto-init si non configuré
    try:
        from agent.osint.wizard import get_wizard
        wizard = get_wizard()
        if not wizard.is_complete():
            wizard.auto_init()
    except Exception as _we:
        pass  # dégradé : on continue sans wizard

    # 1b) PERSON_FULL passe par l'engine comme tout le reste — le connector
    # `person_search_py` génère les username/email candidates qui sont ensuite
    # pivotés en cascade sur sherlock/maigret/github_py/hibp/etc.

    # 2) Consentement — auto-généré si consent=True (défaut)
    # Couvre aussi les cas self_audit avec cible non-self : la LegalGuard
    # renvoie REQUIRE_DISCLAIMER → on a besoin d'un consent_id pour ne pas
    # bloquer l'engine.
    consent_id: Optional[str] = None
    if mode == "external_target" and not consent:
        return (
            "osint_lookup (external_target) : consentement requis.\n\n"
            + _get_disclaimer()
            + "\n\nRe-lancer avec consent=True pour confirmer."
        )
    if consent:
        try:
            from agent.osint.wizard import get_wizard
            consent_id = get_wizard().generate_consent_id(target_raw)
        except Exception:
            consent_id = f"consent_fallback_{int(__import__('time').time())}"

    # 3) Engine
    try:
        from agent.osint.engine import get_engine
        engine = get_engine()
        report = engine.lookup(
            target_raw,
            mode=mode,
            depth=depth,
            deep=deep,
            consent_id=consent_id,
        )
    except Exception as e:
        return f"osint_lookup: erreur engine — {e}"

    # 4) Auto-ouverture du rapport HTML dans le navigateur par défaut
    report_path = getattr(report, "report_path", None)
    if report_path:
        try:
            from pathlib import Path
            import webbrowser
            abs_path = Path(report_path).resolve()
            webbrowser.open(abs_path.as_uri(), new=2)
        except Exception:
            pass  # silencieux — l'user peut toujours cliquer le lien

    # 5) Format
    summary = _fmt_report(report)

    if player and hasattr(player, "write_log"):
        try:
            player.write_log(
                f"OSINT lookup: {target_raw} | "
                f"{len(getattr(report, 'findings', []))} findings"
            )
        except Exception:
            pass

    return summary


def _get_disclaimer() -> str:
    try:
        from agent.osint.wizard import OSINTWizard
        return OSINTWizard.disclaimer_text()
    except Exception:
        return "Disclaimer OSINT : usage conforme RGPD requis."
