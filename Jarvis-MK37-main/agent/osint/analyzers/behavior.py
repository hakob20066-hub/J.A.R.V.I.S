"""
BehaviorAnalyzer — empreinte comportementale depuis les findings agrégés.

Détecte : timezone, langue dominante, cadence posts, topics centraux.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


# Mots français vs anglais pour détection langue rapide
FR_HINTS = {"le", "la", "les", "de", "des", "et", "un", "une", "que", "qui",
            "pour", "avec", "sur", "dans", "mais", "ou", "où", "ça", "c'est",
            "j'ai", "tu", "vous", "nous", "ils", "elle", "il", "merci", "salut"}
EN_HINTS = {"the", "and", "for", "you", "with", "this", "that", "have", "are",
            "but", "not", "from", "what", "when", "where", "who", "your",
            "it's", "i'm", "we're", "they", "thanks", "hello"}


@dataclass
class BehaviorProfile:
    timezone:        Optional[str] = None         # ex: "UTC+1"
    language:        Optional[str] = None         # "fr" | "en" | "other"
    language_scores: dict = field(default_factory=dict)
    posts_per_day:   float = 0.0
    weekday_ratio:   float = 0.0                  # 0..1, % posts en semaine
    most_active_hour: Optional[int] = None
    topics:          list = field(default_factory=list)  # top keywords
    sample_count:    int = 0

    def to_dict(self) -> dict:
        return {
            "timezone":         self.timezone,
            "language":         self.language,
            "language_scores":  self.language_scores,
            "posts_per_day":    round(self.posts_per_day, 2),
            "weekday_ratio":    round(self.weekday_ratio, 2),
            "most_active_hour": self.most_active_hour,
            "topics":           self.topics[:10],
            "sample_count":     self.sample_count,
        }


class BehaviorAnalyzer:

    def analyze(self, findings: list) -> BehaviorProfile:
        prof = BehaviorProfile()
        if not findings:
            return prof

        timestamps: list[datetime] = []
        texts: list[str] = []

        for f in findings:
            extracted = getattr(f, "extracted", {}) or {}
            # Texte
            for key in ("text", "tweet", "caption", "description", "summary",
                        "captions_preview", "title", "abstract"):
                v = extracted.get(key)
                if isinstance(v, str) and len(v) > 5:
                    texts.append(v)
            # Timestamp
            for key in ("date", "datetime", "created_at", "timestamp"):
                v = extracted.get(key)
                if v:
                    dt = self._parse_dt(v)
                    if dt:
                        timestamps.append(dt)

        prof.sample_count = len(texts) + len(timestamps)
        if texts:
            prof.language, prof.language_scores = self._detect_language(texts)
            prof.topics = self._extract_topics(texts)
        if timestamps:
            prof.posts_per_day = self._posts_per_day(timestamps)
            prof.weekday_ratio = self._weekday_ratio(timestamps)
            prof.most_active_hour = self._most_active_hour(timestamps)
            prof.timezone = self._infer_tz(prof.most_active_hour) if prof.most_active_hour is not None else None
        return prof

    # ---------- helpers ----------

    @staticmethod
    def _parse_dt(v) -> Optional[datetime]:
        if isinstance(v, (int, float)):
            try:
                return datetime.fromtimestamp(v, tz=timezone.utc)
            except Exception:
                return None
        if not isinstance(v, str):
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d", "%Y:%m:%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(v.split("+")[0].strip(), fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _detect_language(texts: list[str]) -> tuple[str, dict]:
        all_text = " ".join(texts).lower()
        words = re.findall(r"\b[a-zà-ÿ']+\b", all_text)
        if not words:
            return ("other", {})
        fr = sum(1 for w in words if w in FR_HINTS)
        en = sum(1 for w in words if w in EN_HINTS)
        scores = {"fr": fr, "en": en}
        if fr == 0 and en == 0:
            return ("other", scores)
        return ("fr" if fr > en else "en", scores)

    @staticmethod
    def _extract_topics(texts: list[str], top_n: int = 10) -> list[str]:
        all_text = " ".join(texts).lower()
        words = re.findall(r"\b[a-zà-ÿ']{4,}\b", all_text)
        STOP = {"this", "that", "with", "from", "they", "have", "been",
                "were", "where", "when", "what", "your", "their", "them",
                "dans", "pour", "avec", "vous", "nous", "elle", "leur"}
        words = [w for w in words if w not in STOP]
        return [w for w, _ in Counter(words).most_common(top_n)]

    @staticmethod
    def _posts_per_day(timestamps: list[datetime]) -> float:
        if len(timestamps) < 2:
            return float(len(timestamps))
        ts = sorted(timestamps)
        span = (ts[-1] - ts[0]).total_seconds() / 86400.0
        return len(timestamps) / max(1.0, span)

    @staticmethod
    def _weekday_ratio(timestamps: list[datetime]) -> float:
        weekday = sum(1 for t in timestamps if t.weekday() < 5)
        return weekday / max(1, len(timestamps))

    @staticmethod
    def _most_active_hour(timestamps: list[datetime]) -> Optional[int]:
        if not timestamps:
            return None
        c = Counter(t.hour for t in timestamps)
        return c.most_common(1)[0][0]

    @staticmethod
    def _infer_tz(most_active_hour: int) -> str:
        """Pic 12-22h local → calcul offset depuis UTC. Naïf mais utile."""
        # Si pic UTC=20h, et on suppose user pic local 14h → offset = -6
        TYPICAL_PEAK_LOCAL = 18
        offset = (TYPICAL_PEAK_LOCAL - most_active_hour) % 24
        if offset > 12:
            offset -= 24
        sign = "+" if offset >= 0 else ""
        return f"UTC{sign}{offset}"
