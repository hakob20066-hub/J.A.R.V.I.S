"""Helpers communs aux wrappers Kali."""
from __future__ import annotations

import re
from typing import Optional

from agent.osint.connectors.base import ConnectorResult, Finding
from agent.osint.target import Target


URL_RE   = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w{2,}\b")
DOMAIN_RE = re.compile(r"\b(?:[\w\-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


def fail(name: str, target: Target, error: str, elapsed_ms: int = 0) -> ConnectorResult:
    return ConnectorResult(
        connector=name, target=target, success=False,
        findings=[], elapsed_ms=elapsed_ms, error=error,
    )


def ok(name: str, target: Target, findings: list[Finding], elapsed_ms: int,
       raw: Optional[dict] = None) -> ConnectorResult:
    return ConnectorResult(
        connector=name, target=target, success=True,
        findings=findings, elapsed_ms=elapsed_ms, raw=raw,
    )


def parse_urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))  # preserve order, dedup


def parse_emails(text: str) -> list[str]:
    return list(dict.fromkeys(EMAIL_RE.findall(text)))


def parse_domains(text: str) -> list[str]:
    return list(dict.fromkeys(DOMAIN_RE.findall(text)))
