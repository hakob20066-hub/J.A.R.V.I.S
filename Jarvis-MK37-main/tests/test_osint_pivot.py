"""Tests PivotEngine Phase 7.6."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.pivot import PivotEngine
from agent.osint.connectors.base import Finding
from agent.osint.target import TargetNormalizer, TargetType


def test_pivot_extracts_email_from_extracted():
    pe = PivotEngine()
    f = Finding(type="profile", source="github",
                extracted={"email": "fatih@example.com"})
    pivots = pe.extract_pivots(f)
    assert any(p.type == TargetType.EMAIL for p in pivots)


def test_pivot_extracts_url_domain():
    pe = PivotEngine()
    f = Finding(type="account", source="sherlock",
                url="https://github.com/fatih")
    pivots = pe.extract_pivots(f)
    assert any(p.type == TargetType.DOMAIN and p.normalized == "github.com" for p in pivots)


def test_pivot_dedup_same_target():
    pe = PivotEngine()
    f = Finding(type="x", source="y",
                extracted={"email": "a@b.com", "emails": ["a@b.com"]})
    pivots = pe.extract_pivots(f)
    assert len(pivots) == 1


def test_pivot_max_per_finding():
    pe = PivotEngine(max_pivots_per_finding=2)
    f = Finding(type="x", source="y", extracted={
        "emails": ["a@x.com", "b@x.com", "c@x.com", "d@x.com"]
    })
    pivots = pe.extract_pivots(f)
    assert len(pivots) <= 2


def test_pivot_explicit_pivot_target():
    pe = PivotEngine()
    explicit = TargetNormalizer.detect("explicit@target.com")
    f = Finding(type="x", source="y", pivot_target=explicit)
    pivots = pe.extract_pivots(f)
    assert any(p.normalized == "explicit@target.com" for p in pivots)


def test_pivot_ignores_low_confidence():
    pe = PivotEngine()
    f = Finding(type="x", source="y", extracted={"name": "..."})  # detect → unknown
    pivots = pe.extract_pivots(f)
    assert all(p.is_known for p in pivots)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
