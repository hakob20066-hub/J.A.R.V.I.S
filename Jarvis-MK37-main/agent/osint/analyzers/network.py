"""
NetworkMapper — graphe relationnel depuis findings.

Détecte : co-mentions, geo-clusters, triangulation identité (entities récurrentes).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class NetworkGraph:
    nodes:           list[dict] = field(default_factory=list)   # {id, type, label, weight}
    edges:           list[dict] = field(default_factory=list)   # {src, dst, type, weight}
    co_mentions:     dict       = field(default_factory=dict)   # entity → count
    geo_clusters:    list[list] = field(default_factory=list)   # liste de groupes [(lat, lon), ...]
    triangulations:  list[dict] = field(default_factory=list)   # {entity, mentions, sources}

    def to_dict(self) -> dict:
        return {
            "nodes": self.nodes, "edges": self.edges,
            "co_mentions": dict(list(self.co_mentions.items())[:50]),
            "geo_clusters": [list(c) for c in self.geo_clusters[:20]],
            "triangulations": self.triangulations[:50],
        }


class NetworkMapper:

    def analyze(self, findings: list) -> NetworkGraph:
        g = NetworkGraph()
        if not findings:
            return g

        # 1) Nodes : 1 par source unique + 1 par entité référencée
        seen_nodes: dict[str, dict] = {}
        co_mention_counter: Counter = Counter()
        edges_set: set = set()
        geo_points: list[tuple[float, float]] = []
        entity_sources: defaultdict = defaultdict(set)

        for f in findings:
            ftype = getattr(f, "type", "unknown")
            source = getattr(f, "source", "?")
            extracted = getattr(f, "extracted", {}) or {}

            # Source-node
            sid = f"src::{source}"
            if sid not in seen_nodes:
                seen_nodes[sid] = {"id": sid, "type": "source", "label": source, "weight": 0}
            seen_nodes[sid]["weight"] += 1

            # Entités référencées dans extracted
            for key, val in extracted.items():
                if not isinstance(val, str) or len(val) < 3 or len(val) > 200:
                    continue
                if key not in ("email", "username", "domain", "subdomain", "ip",
                               "phone", "url", "address", "host", "site"):
                    continue
                eid = f"{key}::{val.lower()}"
                if eid not in seen_nodes:
                    seen_nodes[eid] = {"id": eid, "type": key, "label": val, "weight": 0}
                seen_nodes[eid]["weight"] += 1
                co_mention_counter[val.lower()] += 1
                entity_sources[val.lower()].add(source)

                # Edge source → entity
                edge_key = (sid, eid, ftype)
                if edge_key not in edges_set:
                    edges_set.add(edge_key)
                    g.edges.append({"src": sid, "dst": eid,
                                    "type": ftype, "weight": 1.0})

            # Geo
            lat = extracted.get("latitude") or extracted.get("lat")
            lon = extracted.get("longitude") or extracted.get("lon")
            try:
                if lat is not None and lon is not None:
                    geo_points.append((float(lat), float(lon)))
            except (TypeError, ValueError):
                pass

        g.nodes = list(seen_nodes.values())
        g.co_mentions = dict(co_mention_counter.most_common(50))

        # 2) Triangulation : entités citées par >= 2 sources distinctes
        for entity, sources in entity_sources.items():
            if len(sources) >= 2:
                g.triangulations.append({
                    "entity":   entity,
                    "sources":  sorted(sources),
                    "mentions": co_mention_counter[entity],
                })

        # 3) Geo clusters naïfs : grid 0.05° (~5 km)
        g.geo_clusters = self._cluster_geo(geo_points)
        return g

    @staticmethod
    def _cluster_geo(points: list[tuple[float, float]],
                     bucket: float = 0.05) -> list[list[tuple[float, float]]]:
        buckets: defaultdict = defaultdict(list)
        for lat, lon in points:
            key = (round(lat / bucket), round(lon / bucket))
            buckets[key].append((lat, lon))
        return [pts for pts in buckets.values() if len(pts) >= 1]
