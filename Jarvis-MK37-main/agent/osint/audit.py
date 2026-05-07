"""
OSINT audit log JSONL signé HMAC-SHA256.

Voir [[14-Phases/phase7.6-audit-log-hmac]].
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR    = _base_dir()
AUDIT_PATH  = BASE_DIR / "memory" / "osint_audit.log"
KEY_PATH    = BASE_DIR / "memory" / ".osint_audit_key"
MAX_SIZE_MB = 10
_lock       = threading.Lock()


def _get_or_create_key() -> bytes:
    """Clé HMAC persistée localement (64 octets random)."""
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(64)
    KEY_PATH.write_bytes(key)
    try:
        os.chmod(KEY_PATH, 0o600)  # Linux/Mac
    except Exception:
        pass
    return key


def _rotate_if_needed(path: Path) -> None:
    """Rotation par taille : >10 MB → archive .1, .2, ..."""
    if not path.exists():
        return
    if path.stat().st_size < MAX_SIZE_MB * 1024 * 1024:
        return
    for i in range(5, 0, -1):
        old = path.with_suffix(f".log.{i}")
        new = path.with_suffix(f".log.{i+1}")
        if old.exists():
            old.replace(new)
    path.replace(path.with_suffix(".log.1"))


class OSINTAuditLogger:
    """Append-only JSONL signé HMAC. Hashing target sensible."""

    def __init__(self, path: Path = AUDIT_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key = _get_or_create_key()

    def log(
        self,
        target_hash:   str,
        target_type:   str,
        mode:          str,
        depth:         int,
        sources:       list[str],
        findings_count: int = 0,
        consent_id:    Optional[str] = None,
        extra:         Optional[dict] = None,
    ) -> dict:
        entry = {
            "ts":             time.time(),
            "target_hash":    target_hash,
            "target_type":    target_type,
            "mode":           mode,
            "depth":          depth,
            "sources":        sources,
            "findings_count": findings_count,
            "consent":        consent_id,
        }
        if extra:
            entry.update(extra)
        # Sign
        payload = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        entry["hmac"] = hmac.new(self._key, payload, hashlib.sha256).hexdigest()

        with _lock:
            _rotate_if_needed(self.path)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def verify(self, entry: dict) -> bool:
        """Vérifie la signature HMAC d'une entry chargée du log."""
        sig = entry.pop("hmac", None)
        if not sig:
            return False
        payload = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        expected = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def tail(self, n: int = 50) -> list[dict]:
        """Lit les N dernières entries via streaming (pas de chargement complet)."""
        from collections import deque
        if not self.path.exists():
            return []
        last: deque = deque(maxlen=n)
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return list(last)


_LOGGER_SINGLETON: Optional[OSINTAuditLogger] = None


def get_audit_logger() -> OSINTAuditLogger:
    global _LOGGER_SINGLETON
    if _LOGGER_SINGLETON is None:
        _LOGGER_SINGLETON = OSINTAuditLogger()
    return _LOGGER_SINGLETON
