"""
LegalGuard — gating self_audit vs external_target.

Voir [[14-Phases/phase7.6-safety-legal-guard]].
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from agent.osint.target import Target, TargetType


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR        = _base_dir()
SELF_IDENTITIES = BASE_DIR / "config" / "osint_self_identities.json"
CONSENT_LOG     = BASE_DIR / "memory" / "osint_consent.log"
RATE_STATE      = BASE_DIR / "memory" / "osint_rate_state.json"

# Lock décision : 5 lookups external_target MAX par jour.
EXTERNAL_DAILY_LIMIT = 5


class LegalDecision(str, Enum):
    ALLOW                     = "allow"
    REQUIRE_DISCLAIMER        = "require_disclaimer"
    BLOCKED_RATE_LIMIT        = "blocked_rate_limit"
    BLOCKED_DEFAULT_REFUSAL   = "blocked_default_refusal"  # face recognition, address neighbors


@dataclass
class LegalCheck:
    decision: LegalDecision
    reason:   str
    mode:     str
    is_self:  bool
    consent_id: Optional[str] = None


def _load_self_identities() -> dict:
    if not SELF_IDENTITIES.exists():
        return {}
    try:
        return json.loads(SELF_IDENTITIES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_rate_state() -> dict:
    if not RATE_STATE.exists():
        return {}
    try:
        return json.loads(RATE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_rate_state(state: dict) -> None:
    RATE_STATE.parent.mkdir(parents=True, exist_ok=True)
    RATE_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


class LegalGuard:
    """Gate les lookups OSINT selon mode + type cible + identités self déclarées."""

    def __init__(self):
        self.identities = _load_self_identities()

    def reload(self) -> None:
        self.identities = _load_self_identities()

    # ---------- self detection ----------

    def is_self(self, target: Target) -> bool:
        """True si target ∈ self_identities déclarées au wizard."""
        if not self.identities:
            return False
        norm = target.normalized.lower()

        if target.type == TargetType.EMAIL and norm in [e.lower() for e in self.identities.get("emails", [])]:
            return True
        if target.type == TargetType.PHONE and norm in self.identities.get("phones", []):
            return True
        if target.type in (TargetType.USERNAME, TargetType.PSEUDONYM, TargetType.INSTAGRAM_HANDLE,
                           TargetType.SOCIAL_HANDLE):
            for handle in self.identities.get("handles", {}).values():
                if isinstance(handle, str) and handle.lower().lstrip("@") == norm:
                    return True
        if target.type == TargetType.PERSON_FULL:
            full = self.identities.get("full_name", "").lower()
            if full and full == norm.lower():
                return True
        if target.type == TargetType.ADDRESS:
            for addr in self.identities.get("addresses", []):
                if addr.lower() in target.raw.lower():
                    return True
        return False

    # ---------- decision ----------

    def check(self, target: Target, mode: str = "self_audit", deep: bool = False) -> LegalCheck:
        is_self = self.is_self(target)

        # 1) Self → toujours allow
        if is_self:
            return LegalCheck(LegalDecision.ALLOW, "self-target", mode, is_self=True)

        # 2) Cibles "refus par défaut" sauf override
        if mode != "explicit_consent":
            if target.type == TargetType.IMAGE and deep:
                return LegalCheck(
                    LegalDecision.BLOCKED_DEFAULT_REFUSAL,
                    "face recognition refused by default (use mode=explicit_consent)",
                    mode, is_self=False,
                )

        # 3) External target → rate limit + disclaimer
        if mode == "external_target" or (not is_self and mode == "self_audit"):
            if not self._check_external_quota():
                return LegalCheck(
                    LegalDecision.BLOCKED_RATE_LIMIT,
                    f"external_target daily limit reached ({EXTERNAL_DAILY_LIMIT}/day)",
                    mode, is_self=False,
                )
            return LegalCheck(
                LegalDecision.REQUIRE_DISCLAIMER,
                "external target requires legal disclaimer",
                mode="external_target", is_self=False,
            )

        return LegalCheck(LegalDecision.ALLOW, "default", mode, is_self=is_self)

    # ---------- rate limit external ----------

    def _check_external_quota(self) -> bool:
        state = _load_rate_state()
        today = time.strftime("%Y-%m-%d")
        count = state.get("external", {}).get(today, 0)
        return count < EXTERNAL_DAILY_LIMIT

    def consume_external_quota(self) -> int:
        state = _load_rate_state()
        today = time.strftime("%Y-%m-%d")
        ext = state.setdefault("external", {})
        ext[today] = ext.get(today, 0) + 1
        _save_rate_state(state)
        return ext[today]

    # ---------- consent log ----------

    def record_consent(self, target: Target, popup_version: str = "v1") -> str:
        """Enregistre consentement signé user → consent_id réutilisable dans audit."""
        CONSENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        consent_id = f"consent_{popup_version}_{int(time.time())}"
        entry = {
            "ts":             time.time(),
            "consent_id":     consent_id,
            "target_hash":    target.hash(),
            "target_type":    target.type.value,
            "popup_version":  popup_version,
        }
        with open(CONSENT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return consent_id


_GUARD_SINGLETON: Optional[LegalGuard] = None


def get_legal_guard() -> LegalGuard:
    global _GUARD_SINGLETON
    if _GUARD_SINGLETON is None:
        _GUARD_SINGLETON = LegalGuard()
    return _GUARD_SINGLETON
