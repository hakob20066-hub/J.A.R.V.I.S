"""Tests OSINTAuditLogger Phase 7.6 (HMAC signing)."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.audit import OSINTAuditLogger


def test_log_writes_signed_entry():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.log"
        logger = OSINTAuditLogger(path=path)
        entry = logger.log(
            target_hash="abc123", target_type="email",
            mode="self_audit", depth=2, sources=["sherlock", "holehe"],
            findings_count=5,
        )
        assert "hmac" in entry
        assert len(entry["hmac"]) == 64  # SHA256 hex


def test_verify_passes_for_valid_signature():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.log"
        logger = OSINTAuditLogger(path=path)
        entry = logger.log(target_hash="x", target_type="username",
                           mode="self_audit", depth=1, sources=["sherlock"])
        # verify() consume hmac → on copie d'abord
        copy = dict(entry)
        assert logger.verify(copy) is True


def test_verify_fails_if_tampered():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.log"
        logger = OSINTAuditLogger(path=path)
        entry = logger.log(target_hash="x", target_type="username",
                           mode="self_audit", depth=1, sources=["sherlock"])
        copy = dict(entry)
        copy["mode"] = "external_target"  # tampered
        assert logger.verify(copy) is False


def test_tail_returns_last_n():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.log"
        logger = OSINTAuditLogger(path=path)
        for i in range(5):
            logger.log(target_hash=f"h{i}", target_type="x",
                       mode="self_audit", depth=1, sources=[])
        last = logger.tail(n=3)
        assert len(last) == 3
        assert last[-1]["target_hash"] == "h4"


def test_tail_empty_for_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "absent.log"
        logger = OSINTAuditLogger(path=path)
        # logger init crée la clé mais pas le log
        assert logger.tail(n=10) == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
