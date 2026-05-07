"""
OSINTWizard — step 4.6 (setup obligatoire au 1er boot).

Voir [[14-Phases/phase7.6-wizard-step-4.6]].

Responsabilités :
  1. Vérifier si le setup a été complété (config/osint_wizard_done.json)
  2. Sauvegarder les self_identities (config/osint_self_identities.json)
  3. Générer un consent_id pour les lookups external_target
  4. Retourner un résumé lisible de l'état courant
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR         = _base_dir()
WIZARD_DONE_FILE = BASE_DIR / "config" / "osint_wizard_done.json"
IDENTITIES_FILE  = BASE_DIR / "config" / "osint_self_identities.json"


class OSINTWizard:
    """Gère le setup initial OSINT (step 4.6) et le consentement externe."""

    # ---------- state ----------

    def is_complete(self) -> bool:
        """True si le wizard a été complété au moins une fois."""
        if not WIZARD_DONE_FILE.exists():
            return False
        try:
            d = json.loads(WIZARD_DONE_FILE.read_text(encoding="utf-8"))
            return bool(d.get("done"))
        except Exception:
            return False

    def get_identities(self) -> dict:
        """Retourne les self_identities sauvegardées (dict vide si aucune)."""
        if not IDENTITIES_FILE.exists():
            return {}
        try:
            return json.loads(IDENTITIES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    # ---------- setup ----------

    def save_identities(self, identities: dict) -> None:
        """
        Sauvegarde les identités self et marque le wizard comme complété.

        identities = {
          "name":      "Jean Dupont",
          "emails":    ["jean@example.com"],
          "handles":   ["jeandupont", "@jean_d"],
          "phones":    ["+33612345678"],
          "addresses": ["12 rue de la Paix, Paris"],
        }
        """
        IDENTITIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        IDENTITIES_FILE.write_text(
            json.dumps(identities, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        WIZARD_DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
        WIZARD_DONE_FILE.write_text(
            json.dumps({"done": True, "ts": time.time()}, indent=2),
            encoding="utf-8",
        )
        # Reload the guard so it picks up new identities
        try:
            from agent.osint.safety import get_legal_guard
            get_legal_guard().reload()
        except Exception:
            pass

    def auto_init(self) -> None:
        """Initialise le wizard avec des identités vides si pas encore fait."""
        if not self.is_complete():
            self.save_identities({})

    # ---------- consent ----------

    def generate_consent_id(
        self,
        target_raw: str,
        popup_version: str = "v1",
    ) -> str:
        """
        Enregistre le consentement user pour un external_target lookup.
        Retourne un consent_id à passer à engine.lookup_async().
        """
        from agent.osint.target import TargetNormalizer
        from agent.osint.safety import get_legal_guard
        target = TargetNormalizer.detect(target_raw)
        return get_legal_guard().record_consent(target, popup_version=popup_version)

    # ---------- summary ----------

    def setup_summary(self) -> str:
        """Retourne un résumé texte de l'état courant du wizard."""
        if not self.is_complete():
            return (
                "OSINT wizard non configuré. "
                "Appelle osint_wizard_setup() ou lance le wizard interactif."
            )
        ids = self.get_identities()
        parts: list[str] = ["OSINT wizard ✓"]
        if ids.get("name"):
            parts.append(f"Nom: {ids['name']}")
        emails = ids.get("emails") or []
        handles = ids.get("handles") or []
        phones = ids.get("phones") or []
        if emails:
            parts.append(f"Emails self: {', '.join(emails[:3])}")
        if handles:
            parts.append(f"Handles: {', '.join(handles[:5])}")
        if phones:
            parts.append(f"Téléphones: {', '.join(phones[:2])}")
        if not (emails or handles or phones):
            parts.append("(aucune identité déclarée — mode self_audit limité)")
        return " | ".join(parts)

    # ---------- disclaimer text ----------

    @staticmethod
    def disclaimer_text() -> str:
        return (
            "AVERTISSEMENT LÉGAL OSINT\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "L'utilisation de cet outil pour rechercher des informations\n"
            "sur des tiers doit respecter le RGPD (EU 2016/679) et les\n"
            "lois locales applicables.\n\n"
            "• Vous êtes responsable de l'usage des données collectées.\n"
            "• Maximum 5 lookups external_target par jour.\n"
            "• Les cibles image (reconnaissance faciale) sont refusées\n"
            "  sauf consentement explicite.\n"
            "• Toute recherche est auditée localement (HMAC).\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "En continuant vous acceptez ces conditions."
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_WIZARD_SINGLETON: Optional[OSINTWizard] = None


def get_wizard() -> OSINTWizard:
    global _WIZARD_SINGLETON
    if _WIZARD_SINGLETON is None:
        _WIZARD_SINGLETON = OSINTWizard()
    return _WIZARD_SINGLETON


def reset_wizard() -> None:
    global _WIZARD_SINGLETON
    _WIZARD_SINGLETON = None
