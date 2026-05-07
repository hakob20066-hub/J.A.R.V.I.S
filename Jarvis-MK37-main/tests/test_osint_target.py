"""Tests TargetNormalizer Phase 7.6."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.target import TargetNormalizer, TargetType


def detect(s):
    return TargetNormalizer.detect(s)


def test_email():
    t = detect("Fatih@Example.COM")
    assert t.type == TargetType.EMAIL
    assert t.normalized == "fatih@example.com"


def test_ip4():
    t = detect("8.8.8.8")
    assert t.type == TargetType.IP

def test_ip4_invalid():
    # 999 invalid octet → not IP
    t = detect("999.0.0.0")
    assert t.type != TargetType.IP


def test_btc_addr():
    t = detect("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    assert t.type == TargetType.CRYPTO
    assert t.metadata.get("chain") == "BTC"


def test_eth_addr():
    t = detect("0x" + "a" * 40)
    assert t.type == TargetType.CRYPTO
    assert t.metadata.get("chain") == "ETH"


def test_phone_with_plus():
    t = detect("+33 6 12 34 56 78")
    assert t.type == TargetType.PHONE


def test_phone_digits_only():
    t = detect("0612345678")
    assert t.type == TargetType.PHONE


def test_instagram_at_handle():
    t = detect("@fatihmakes")
    assert t.type == TargetType.INSTAGRAM_HANDLE
    assert t.normalized == "fatihmakes"


def test_instagram_url():
    t = detect("https://instagram.com/fatihmakes/")
    assert t.type == TargetType.INSTAGRAM_HANDLE
    assert t.normalized == "fatihmakes"


def test_domain():
    t = detect("example.com")
    assert t.type == TargetType.DOMAIN


def test_subdomain():
    t = detect("sub.example.co.uk")
    assert t.type == TargetType.DOMAIN


def test_username_lowercase():
    t = detect("fatihmakes")
    # Sans @, c'est ambigu : domaine sans TLD ou username ?
    # Notre normalizer privilégie username si pas de point
    assert t.type == TargetType.USERNAME
    assert t.normalized == "fatihmakes"


def test_person_full():
    t = detect("Fatih Makes")
    assert t.type == TargetType.PERSON_FULL


def test_address():
    t = detect("12 rue de la Paix Paris")
    assert t.type == TargetType.ADDRESS


def test_unknown():
    t = detect("...")
    assert t.type == TargetType.UNKNOWN


def test_empty():
    t = detect("")
    assert t.type == TargetType.UNKNOWN


def test_target_hash_deterministic():
    t1 = detect("fatih@x.com")
    t2 = detect("FATIH@X.COM")
    assert t1.hash() == t2.hash()


def test_target_hash_different_per_type():
    t1 = detect("@user")  # instagram
    t2 = detect("user")   # username
    assert t1.hash() != t2.hash()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
