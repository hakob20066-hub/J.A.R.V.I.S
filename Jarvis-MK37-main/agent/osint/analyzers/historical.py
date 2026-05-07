"""
HistoricalScraper — frise chronologique depuis les findings datés.

Détecte : timeline, snapshots Wayback, évolution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TimelineEvent:
    timestamp: float          # epoch
    iso:       str
    event_type: str
    source:    str
    summary:   str
    url:       Optional[str] = None

    def to_dict(self) -> dict:
        return {"timestamp": self.timestamp, "iso": self.iso,
                "event_type": self.event_type, "source": self.source,
                "summary": self.summary, "url": self.url}


@dataclass
class Timeline:
    events:           list[TimelineEvent] = field(default_factory=list)
    earliest:         Optional[str] = None
    latest:           Optional[str] = None
    wayback_count:    int = 0
    archives_count:   int = 0

    def to_dict(self) -> dict:
        return {
            "events":         [e.to_dict() for e in self.events[:200]],
            "earliest":       self.earliest,
            "latest":         self.latest,
            "wayback_count":  self.wayback_count,
            "archives_count": self.archives_count,
            "total_events":   len(self.events),
        }


class HistoricalScraper:

    def analyze(self, findings: list) -> Timeline:
        tl = Timeline()
        if not findings:
            return tl

        for f in findings:
            extracted = getattr(f, "extracted", {}) or {}
            ftype  = getattr(f, "type", "unknown")
            source = getattr(f, "source", "?")
            url    = getattr(f, "url", None)

            ts = self._extract_ts(extracted)
            if ts is None:
                continue
            iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            summary_parts = []
            for k in ("subdomain", "username", "site", "url", "value", "summary"):
                if extracted.get(k):
                    summary_parts.append(str(extracted[k])[:80])
                    break
            summary = " | ".join(summary_parts) or ftype

            tl.events.append(TimelineEvent(
                timestamp=ts, iso=iso, event_type=ftype,
                source=source, summary=summary, url=url,
            ))

            if "wayback" in source.lower() or "wayback" in (url or "").lower():
                tl.wayback_count += 1
            if "archive" in source.lower():
                tl.archives_count += 1

        tl.events.sort(key=lambda e: e.timestamp)
        if tl.events:
            tl.earliest = tl.events[0].iso
            tl.latest   = tl.events[-1].iso
        return tl

    @staticmethod
    def _extract_ts(extracted: dict) -> Optional[float]:
        for key in ("timestamp", "date", "datetime", "created_at",
                    "DateTimeOriginal", "updated_at"):
            v = extracted.get(key)
            if v is None:
                continue
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                ts = HistoricalScraper._parse_str(v)
                if ts is not None:
                    return ts
        return None

    @staticmethod
    def _parse_str(s: str) -> Optional[float]:
        s = s.strip().split("+")[0].split(".")[0]
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                    "%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
        return None
