"""
OSINTEngine — orchestrateur central Phase 7.6.

Voir [[14-Phases/phase7.6-osint-overview]].

Pipeline :
    target_raw → TargetNormalizer.detect()
              → LegalGuard.check()
              → boucle cascade :
                  for active in queue:
                    connectors = registry.for_target(active)
                    parallel run via AdaptiveScheduler
                    for finding in results:
                        ui_bridge.on_finding()
                        pivots = pivot_engine.extract_pivots(finding)
                        queue.extend(pivots if depth allows)
              → aggregator (dedup) + scorer
              → reporter.build() + persistance
              → audit.log()
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent.osint.audit import OSINTAuditLogger, get_audit_logger
from agent.osint.connectors.base import ConnectorResult, Finding, get_registry
from agent.osint.pivot import PivotEngine
from agent.osint.safety import LegalDecision, get_legal_guard
from agent.osint.scheduler import AdaptiveScheduler
from agent.osint.target import Target, TargetNormalizer
from agent.osint.ui_bridge import OSINTUIBridge, get_ui_bridge


# Lock decisions
MAX_TOTAL_TARGETS = 500
MAX_RUNTIME_SECONDS = 600
DEFAULT_DEPTH = 2
MAX_DEPTH = 3


@dataclass
class OSINTReport:
    target:         Target
    mode:           str
    started_at:     float
    completed_at:   float
    findings:       list[Finding] = field(default_factory=list)
    sources_used:   list[str] = field(default_factory=list)
    sources_failed: list[tuple[str, str]] = field(default_factory=list)
    targets_explored: list[Target] = field(default_factory=list)
    cancelled:      bool = False
    error:          Optional[str] = None
    report_dir:     Optional[Path] = None
    report_path:    Optional[Path] = None  # chemin absolu du .html
    analyzers:      dict = field(default_factory=dict)  # behavior/network/historical/metadata

    @property
    def duration_ms(self) -> int:
        return int((self.completed_at - self.started_at) * 1000)

    def to_dict(self) -> dict:
        return {
            "target": {
                "raw": self.target.raw,
                "type": self.target.type.value,
                "normalized": self.target.normalized,
                "hash": self.target.hash(),
            },
            "mode": self.mode,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "sources_used": self.sources_used,
            "sources_failed": self.sources_failed,
            "targets_explored": [
                {"type": t.type.value, "normalized": t.normalized} for t in self.targets_explored
            ],
            "cancelled": self.cancelled,
            "error": self.error,
        }


class OSINTEngine:
    """Singleton orchestrateur. Cascade pivot continue."""

    def __init__(
        self,
        ui_bridge: Optional[OSINTUIBridge] = None,
        scheduler: Optional[AdaptiveScheduler] = None,
        pivot_engine: Optional[PivotEngine] = None,
        audit_logger: Optional[OSINTAuditLogger] = None,
    ):
        self.ui_bridge = ui_bridge or get_ui_bridge()
        self.scheduler = scheduler or AdaptiveScheduler()
        self.pivot_engine = pivot_engine or PivotEngine()
        self.audit_logger = audit_logger or get_audit_logger()
        self.guard = get_legal_guard()
        self._cancel_flag = threading.Event()

    # ---------- public ----------

    def cancel(self) -> None:
        self._cancel_flag.set()

    async def lookup_async(
        self,
        target_raw: str,
        mode: str = "self_audit",
        depth: int = DEFAULT_DEPTH,
        deep: bool = False,
        consent_id: Optional[str] = None,
        reset_cancel: bool = True,
    ) -> OSINTReport:
        if reset_cancel:
            self._cancel_flag.clear()
        depth = max(1, min(MAX_DEPTH, depth))
        started = time.time()

        # 1) Normalize
        target = TargetNormalizer.detect(target_raw)
        report = OSINTReport(target=target, mode=mode, started_at=started, completed_at=started)

        if not target.is_known:
            report.error = f"target type unknown: {target_raw!r}"
            self.ui_bridge.on_error(report.error)
            report.completed_at = time.time()
            return report

        # 2) Legal check
        legal = self.guard.check(target, mode=mode, deep=deep)
        if legal.decision == LegalDecision.BLOCKED_RATE_LIMIT:
            report.error = legal.reason
            self.ui_bridge.on_error(report.error)
            report.completed_at = time.time()
            return report
        if legal.decision == LegalDecision.BLOCKED_DEFAULT_REFUSAL:
            report.error = legal.reason
            self.ui_bridge.on_error(report.error)
            report.completed_at = time.time()
            return report
        if legal.decision == LegalDecision.REQUIRE_DISCLAIMER and not consent_id:
            report.error = "external_target requires consent_id (popup not signed)"
            self.ui_bridge.on_error(report.error)
            report.completed_at = time.time()
            return report

        if mode == "external_target":
            self.guard.consume_external_quota()

        # 3) UI start
        self.ui_bridge.on_start(target, mode)

        # 4) Cascade
        registry = get_registry()
        active_queue: list[tuple[Target, int]] = [(target, 0)]
        explored: set[str] = set()
        findings: list[Finding] = []
        sources_used: set[str] = set()
        sources_failed: list[tuple[str, str]] = []

        deadline = started + MAX_RUNTIME_SECONDS

        while active_queue:
            if self._cancel_flag.is_set():
                report.cancelled = True
                break
            if time.time() > deadline:
                report.error = "max_runtime exceeded"
                break
            if len(explored) >= MAX_TOTAL_TARGETS:
                report.error = f"max_total_targets ({MAX_TOTAL_TARGETS}) reached"
                break

            current, t_depth = active_queue.pop(0)
            key = f"{current.type.value}:{current.normalized}"
            if key in explored:
                continue
            explored.add(key)
            report.targets_explored.append(current)

            # Sélectionne connecteurs disponibles pour ce type
            connectors = registry.for_target(current)
            if not connectors:
                continue

            # Run en parallèle via scheduler
            coros = [c.query(current) for c in connectors]
            total = len(coros)
            done_count = 0

            for fut in asyncio.as_completed(coros):
                if self._cancel_flag.is_set():
                    break
                try:
                    result: ConnectorResult = await fut
                except Exception as e:
                    sources_failed.append(("unknown", str(e)))
                    continue
                done_count += 1
                self.ui_bridge.on_progress(done_count, total)

                if result.success:
                    sources_used.add(result.connector)
                    self.ui_bridge.on_connector_done(result.connector, True, len(result.findings))
                    for f in result.findings:
                        findings.append(f)
                        self.ui_bridge.on_finding(f)

                        # Auto-pivot
                        if t_depth + 1 < depth:
                            for piv in self.pivot_engine.extract_pivots(f):
                                pkey = f"{piv.type.value}:{piv.normalized}"
                                if pkey not in explored:
                                    active_queue.append((piv, t_depth + 1))
                else:
                    sources_failed.append((result.connector, result.error or "failed"))
                    self.ui_bridge.on_connector_done(result.connector, False, 0)

        # 5) Finalize
        report.findings = findings
        report.sources_used = sorted(sources_used)
        report.sources_failed = sources_failed

        # 5b) Analyzers cross-cutting
        try:
            from agent.osint.analyzers import run_all as _run_all
            report.analyzers = {
                k: v.to_dict() for k, v in _run_all(findings).items()
            }
        except Exception as _e:
            report.analyzers = {"_error": str(_e)}

        report.completed_at = time.time()

        # 6) Audit
        self.audit_logger.log(
            target_hash=target.hash(),
            target_type=target.type.value,
            mode=mode,
            depth=depth,
            sources=report.sources_used,
            findings_count=len(findings),
            consent_id=consent_id,
            extra={"duration_ms": report.duration_ms,
                   "cancelled": report.cancelled,
                   "targets_explored": len(report.targets_explored)},
        )

        # 7) Reporter HTML
        try:
            from agent.osint.reporter import get_reporter
            html_path = get_reporter().build(report)
            # Toujours stocker le chemin ABSOLU pour que ouverture navigateur
            # marche depuis n'importe où (sinon Edge interprète "memory\..."
            # comme un hostname et renvoie DNS_PROBE_FINISHED_NXDOMAIN).
            html_path = Path(html_path).resolve()
            report.report_path = html_path
            report.report_dir  = html_path.parent
            self.ui_bridge.on_complete(str(html_path))
        except Exception as _re:
            self.ui_bridge.on_complete("")

        return report

    def lookup(self, target_raw: str, **kw) -> OSINTReport:
        """Sync wrapper."""
        try:
            loop = asyncio.get_running_loop()
            # déjà dans un loop : run dans un thread dédié
            import threading
            result = {}
            def runner():
                result["r"] = asyncio.run(self.lookup_async(target_raw, **kw))
            t = threading.Thread(target=runner)
            t.start(); t.join()
            return result["r"]
        except RuntimeError:
            return asyncio.run(self.lookup_async(target_raw, **kw))


_ENGINE_SINGLETON: Optional[OSINTEngine] = None


def get_engine() -> OSINTEngine:
    global _ENGINE_SINGLETON
    if _ENGINE_SINGLETON is None:
        _ENGINE_SINGLETON = OSINTEngine()
    return _ENGINE_SINGLETON


def reset_engine() -> None:
    global _ENGINE_SINGLETON
    _ENGINE_SINGLETON = None
