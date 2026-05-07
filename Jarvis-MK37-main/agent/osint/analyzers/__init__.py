"""
OSINT analyzers cross-cutting (post-process sur findings agrégés).

Voir [[14-Phases/phase7.6-analyzers]].
"""
from agent.osint.analyzers.behavior import BehaviorAnalyzer, BehaviorProfile
from agent.osint.analyzers.network import NetworkMapper, NetworkGraph
from agent.osint.analyzers.historical import HistoricalScraper, Timeline
from agent.osint.analyzers.metadata import MetadataExtractor, MetadataReport

__all__ = [
    "BehaviorAnalyzer", "BehaviorProfile",
    "NetworkMapper", "NetworkGraph",
    "HistoricalScraper", "Timeline",
    "MetadataExtractor", "MetadataReport",
]


def run_all(findings: list) -> dict:
    """Lance les 4 analyzers sur les findings, retourne dict des profils."""
    return {
        "behavior":   BehaviorAnalyzer().analyze(findings),
        "network":    NetworkMapper().analyze(findings),
        "historical": HistoricalScraper().analyze(findings),
        "metadata":   MetadataExtractor().analyze(findings),
    }
