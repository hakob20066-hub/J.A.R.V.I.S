"""
OSINTUIBridge — pousse événements moteur → JarvisUI (panel + window report).

Voir [[14-Phases/phase7.6-ui-panel-gauche]].
"""
from __future__ import annotations

from typing import Optional

from agent.osint.connectors.base import Finding
from agent.osint.target import Target


class OSINTUIBridge:
    """Pas de dépendance directe à JarvisUI. Tient un weak ref."""

    def __init__(self, ui=None):
        self.ui = ui
        self._enabled = ui is not None

    def attach(self, ui) -> None:
        self.ui = ui
        self._enabled = True

    def detach(self) -> None:
        self._enabled = False

    # ---------- events ----------

    def on_start(self, target: Target, mode: str) -> None:
        if not self._enabled or self.ui is None:
            return
        try:
            self.ui.osint_panel_start(target.normalized, mode, target.type.value)
        except Exception:
            pass

    def on_progress(self, current: int, total: int) -> None:
        if not self._enabled or self.ui is None:
            return
        pct = (current / total * 100.0) if total > 0 else 0.0
        try:
            self.ui.osint_panel_progress(round(pct, 1), current, total)
        except Exception:
            pass

    def on_connector_done(self, connector: str, success: bool, count: int) -> None:
        if not self._enabled or self.ui is None:
            return
        try:
            self.ui.osint_panel_connector_done(connector, success, count)
        except Exception:
            pass

    def on_finding(self, finding: Finding) -> None:
        if not self._enabled or self.ui is None:
            return
        try:
            self.ui.osint_panel_finding(finding.type, finding.source, finding.url, finding.confidence)
        except Exception:
            pass

    def on_complete(self, report_path: str) -> None:
        if not self._enabled or self.ui is None:
            return
        try:
            self.ui.osint_panel_complete(report_path)
        except Exception:
            pass

    def on_error(self, error: str) -> None:
        if not self._enabled or self.ui is None:
            return
        try:
            self.ui.osint_panel_error(error)
        except Exception:
            pass

    def on_cancel(self) -> None:
        if not self._enabled or self.ui is None:
            return
        try:
            self.ui.osint_panel_cancel()
        except Exception:
            pass


_BRIDGE_SINGLETON: Optional[OSINTUIBridge] = None


def get_ui_bridge() -> OSINTUIBridge:
    global _BRIDGE_SINGLETON
    if _BRIDGE_SINGLETON is None:
        _BRIDGE_SINGLETON = OSINTUIBridge()
    return _BRIDGE_SINGLETON
