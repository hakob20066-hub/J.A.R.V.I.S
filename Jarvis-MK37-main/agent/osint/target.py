"""
Target normalization — 12 types auto-détectés.

Voir [[14-Phases/phase7.6-targets-12]].
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class TargetType(str, Enum):
    EMAIL            = "email"
    DOMAIN           = "domain"
    IP               = "ip"
    USERNAME         = "username"
    PSEUDONYM        = "pseudonym"      # alias of username, explicit
    INSTAGRAM_HANDLE = "instagram_handle"
    SOCIAL_HANDLE    = "social_handle"  # twitter/tiktok/etc
    PERSON_FULL      = "person_full"    # name + firstname (+ city)
    ADDRESS          = "address"
    PHONE            = "phone"
    CRYPTO           = "crypto"
    IMAGE            = "image"
    UNKNOWN          = "unknown"


@dataclass
class Target:
    raw:        str
    type:       TargetType
    normalized: str
    confidence: float = 1.0
    metadata:   dict  = field(default_factory=dict)

    @property
    def is_known(self) -> bool:
        return self.type != TargetType.UNKNOWN

    def hash(self) -> str:
        import hashlib
        return hashlib.sha256(f"{self.type.value}:{self.normalized}".encode("utf-8")).hexdigest()[:16]


# ---------- regex patterns ----------

RE_EMAIL    = re.compile(r"^[\w.\-+]+@[\w.\-]+\.\w{2,}$")
RE_IP4      = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
RE_IP6      = re.compile(r"^[0-9a-fA-F:]+$")
RE_DOMAIN   = re.compile(r"^(?:[\w\-]+\.)+[a-z]{2,}$", re.IGNORECASE)
RE_PHONE    = re.compile(r"^\+?[\d\s\-().]{7,}$")
RE_BTC      = re.compile(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}$")
RE_ETH      = re.compile(r"^0x[a-fA-F0-9]{40}$")
RE_IG_URL   = re.compile(r"^(?:https?://)?(?:www\.)?instagram\.com/([\w.]+)/?", re.IGNORECASE)
RE_IG_AT    = re.compile(r"^@([\w.]{2,30})$")
RE_USERNAME = re.compile(r"^[a-zA-Z0-9_.\-]{3,30}$")
RE_PERSON   = re.compile(r"^[A-ZÀ-ÿ][a-zà-ÿ]+(?:[ \-][A-ZÀ-ÿ]?[a-zà-ÿ]+){1,4}$")
RE_ADDRESS  = re.compile(r"\d+\s+\w+|rue|avenue|boulevard|street|road|av\.|bd\.", re.IGNORECASE)


class TargetNormalizer:
    """Détecte le type d'une cible OSINT brute."""

    @classmethod
    def detect(cls, raw: str) -> Target:
        s = (raw or "").strip()
        if not s:
            return Target(raw=raw, type=TargetType.UNKNOWN, normalized="", confidence=0.0)

        # 1) Image path
        if cls._is_image_path(s):
            return Target(raw=raw, type=TargetType.IMAGE, normalized=str(Path(s).resolve()))

        # 2) Email
        if RE_EMAIL.match(s):
            return Target(raw=raw, type=TargetType.EMAIL, normalized=s.lower())

        # 3) IPv4
        if RE_IP4.match(s) and all(0 <= int(o) <= 255 for o in s.split(".")):
            return Target(raw=raw, type=TargetType.IP, normalized=s)

        # 4) Crypto (BTC / ETH)
        if RE_BTC.match(s):
            return Target(raw=raw, type=TargetType.CRYPTO, normalized=s, metadata={"chain": "BTC"})
        if RE_ETH.match(s):
            return Target(raw=raw, type=TargetType.CRYPTO, normalized=s.lower(), metadata={"chain": "ETH"})

        # 5) Phone (avec ou sans préfixe)
        if RE_PHONE.match(s) and any(c.isdigit() for c in s):
            digits = re.sub(r"\D", "", s)
            if 7 <= len(digits) <= 15:
                return Target(raw=raw, type=TargetType.PHONE, normalized="+" + digits if not s.startswith("+") else s)

        # 6) Instagram URL ou @handle
        m = RE_IG_URL.match(s)
        if m:
            return Target(raw=raw, type=TargetType.INSTAGRAM_HANDLE, normalized=m.group(1).lower())
        m = RE_IG_AT.match(s)
        if m:
            return Target(raw=raw, type=TargetType.INSTAGRAM_HANDLE, normalized=m.group(1).lower(), confidence=0.8)

        # 7) Domain
        if RE_DOMAIN.match(s):
            return Target(raw=raw, type=TargetType.DOMAIN, normalized=s.lower())

        # 8) Address (heuristique)
        if RE_ADDRESS.search(s) and len(s.split()) >= 3:
            return Target(raw=raw, type=TargetType.ADDRESS, normalized=s)

        # 9) Person full (au moins 2 mots commençant par majuscule)
        if RE_PERSON.match(s) and len(s.split()) >= 2:
            return Target(raw=raw, type=TargetType.PERSON_FULL, normalized=s)

        # 10) Username / pseudonym (au moins 1 alphanum + ratio alphanum > 50%)
        if RE_USERNAME.match(s):
            alnum = sum(1 for c in s if c.isalnum())
            if alnum > 0 and alnum / len(s) >= 0.5:
                return Target(raw=raw, type=TargetType.USERNAME, normalized=s.lower(), confidence=0.7)

        return Target(raw=raw, type=TargetType.UNKNOWN, normalized=s, confidence=0.0)

    @staticmethod
    def _is_image_path(s: str) -> bool:
        if not any(s.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            return False
        try:
            return Path(s).exists()
        except OSError:
            return False
