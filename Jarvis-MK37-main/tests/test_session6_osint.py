"""
Session 6 OSINT — Tests intégration (wizard + osint_lookup + authority + pipeline).

Groupes :
  A) OSINTWizard (8 tests)
  B) osint_lookup action (8 tests)
  C) authority.json (2 tests)
  D) Pipeline intégration end-to-end mocked (6 tests)
"""
from __future__ import annotations

import json
import sys
import time
import types
import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── path ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
# A) OSINTWizard
# ═══════════════════════════════════════════════════════════════════════════════

class TestOSINTWizard(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Patch file paths inside wizard module
        import agent.osint.wizard as wiz_mod
        self._orig_done = wiz_mod.WIZARD_DONE_FILE
        self._orig_ids  = wiz_mod.IDENTITIES_FILE
        wiz_mod.WIZARD_DONE_FILE = self.tmp_path / "wizard_done.json"
        wiz_mod.IDENTITIES_FILE  = self.tmp_path / "identities.json"
        wiz_mod.reset_wizard()

    def tearDown(self):
        import agent.osint.wizard as wiz_mod
        wiz_mod.WIZARD_DONE_FILE = self._orig_done
        wiz_mod.IDENTITIES_FILE  = self._orig_ids
        wiz_mod.reset_wizard()
        self.tmp.cleanup()

    def _wizard(self):
        from agent.osint.wizard import OSINTWizard
        return OSINTWizard()

    def test_not_complete_by_default(self):
        w = self._wizard()
        self.assertFalse(w.is_complete())

    def test_complete_after_save(self):
        w = self._wizard()
        w.save_identities({"name": "Test User"})
        self.assertTrue(w.is_complete())

    def test_save_writes_identities_file(self):
        import agent.osint.wizard as wiz_mod
        w = self._wizard()
        ids = {"name": "Alice", "emails": ["alice@example.com"], "handles": ["alice99"]}
        w.save_identities(ids)
        data = json.loads(wiz_mod.IDENTITIES_FILE.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "Alice")
        self.assertIn("alice@example.com", data["emails"])

    def test_get_identities_empty_before_setup(self):
        w = self._wizard()
        self.assertEqual(w.get_identities(), {})

    def test_get_identities_after_save(self):
        w = self._wizard()
        w.save_identities({"handles": ["bob"]})
        self.assertEqual(w.get_identities()["handles"], ["bob"])

    def test_auto_init_marks_complete(self):
        w = self._wizard()
        self.assertFalse(w.is_complete())
        w.auto_init()
        self.assertTrue(w.is_complete())

    def test_auto_init_idempotent(self):
        w = self._wizard()
        w.save_identities({"name": "X"})
        w.auto_init()  # Should not overwrite
        self.assertEqual(w.get_identities().get("name"), "X")

    def test_setup_summary_not_complete(self):
        w = self._wizard()
        s = w.setup_summary()
        self.assertIn("non configuré", s.lower())

    def test_setup_summary_complete(self):
        w = self._wizard()
        w.save_identities({"name": "Jean", "emails": ["j@x.com"]})
        s = w.setup_summary()
        self.assertIn("Jean", s)
        self.assertIn("j@x.com", s)

    def test_disclaimer_text_contains_rgpd(self):
        from agent.osint.wizard import OSINTWizard
        txt = OSINTWizard.disclaimer_text()
        self.assertIn("RGPD", txt)
        self.assertIn("5", txt)  # daily limit


# ═══════════════════════════════════════════════════════════════════════════════
# B) osint_lookup action
# ═══════════════════════════════════════════════════════════════════════════════

def _make_report(findings=None, error=None, cancelled=False, sources=None):
    """Helper : construit un OSINTReport-like mock."""
    report = MagicMock()
    report.cancelled = cancelled
    report.error = error
    report.findings = findings or []
    report.sources_used = sources or []
    report.sources_failed = []
    report.targets_explored = []
    report.duration_ms = 42
    report.report_dir = None
    tgt = MagicMock()
    tgt.normalized = "example.com"
    tgt.type.value = "domain"
    report.target = tgt
    return report


class TestOSINTLookupAction(unittest.TestCase):

    def test_no_target_returns_help(self):
        from actions.osint_lookup import osint_lookup
        r = osint_lookup({})
        self.assertIn("target", r.lower())

    def test_external_without_consent_shows_disclaimer(self):
        from actions.osint_lookup import osint_lookup
        r = osint_lookup({"target": "example.com", "mode": "external_target", "consent": False})
        self.assertIn("consentement", r.lower())
        self.assertIn("RGPD", r)

    def test_self_audit_calls_engine(self):
        from actions.osint_lookup import osint_lookup
        report = _make_report()
        mock_engine = MagicMock()
        mock_engine.lookup.return_value = report
        # get_engine est importé lazily dans la fonction → patcher dans le module source
        with patch("agent.osint.engine.get_engine", return_value=mock_engine):
            r = osint_lookup({"target": "example.com", "mode": "self_audit"})
        mock_engine.lookup.assert_called_once()
        self.assertIn("example.com", r)

    def test_engine_error_returns_message(self):
        from actions.osint_lookup import osint_lookup
        mock_engine = MagicMock()
        mock_engine.lookup.side_effect = RuntimeError("engine kaboom")
        with patch("agent.osint.engine.get_engine", return_value=mock_engine):
            r = osint_lookup({"target": "1.2.3.4"})
        self.assertIn("erreur", r.lower())

    def test_report_error_shown(self):
        from actions.osint_lookup import osint_lookup
        report = _make_report(error="max_runtime exceeded")
        mock_engine = MagicMock()
        mock_engine.lookup.return_value = report
        with patch("agent.osint.engine.get_engine", return_value=mock_engine):
            r = osint_lookup({"target": "test.com"})
        self.assertIn("max_runtime", r)

    def test_report_cancelled_shown(self):
        from actions.osint_lookup import osint_lookup
        report = _make_report(cancelled=True)
        mock_engine = MagicMock()
        mock_engine.lookup.return_value = report
        with patch("agent.osint.engine.get_engine", return_value=mock_engine):
            r = osint_lookup({"target": "test.com"})
        self.assertIn("CANCELLED", r)

    def test_findings_formatted(self):
        from actions.osint_lookup import osint_lookup
        f = MagicMock()
        f.type = "breach"
        f.source = "hibp"
        f.extracted = {"breach_name": "Adobe", "date": "2013"}
        report = _make_report(findings=[f], sources=["hibp"])
        mock_engine = MagicMock()
        mock_engine.lookup.return_value = report
        with patch("agent.osint.engine.get_engine", return_value=mock_engine):
            r = osint_lookup({"target": "user@example.com"})
        self.assertIn("breach", r)
        self.assertIn("hibp", r)

    def test_external_with_consent_calls_engine(self):
        from actions.osint_lookup import osint_lookup
        report = _make_report()
        mock_engine = MagicMock()
        mock_engine.lookup.return_value = report
        with patch("agent.osint.engine.get_engine", return_value=mock_engine), \
             patch("agent.osint.wizard.get_wizard") as mock_wiz:
            mock_wiz.return_value.generate_consent_id.return_value = "consent_v1_123"
            mock_wiz.return_value.is_complete.return_value = True
            r = osint_lookup({"target": "example.com", "mode": "external_target", "consent": True})
        mock_engine.lookup.assert_called_once()
        call_kwargs = mock_engine.lookup.call_args
        self.assertEqual(call_kwargs[1].get("consent_id"), "consent_v1_123")


# ═══════════════════════════════════════════════════════════════════════════════
# C) Authority config
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthorityConfig(unittest.TestCase):

    def _load_authority(self) -> dict:
        path = ROOT / "config" / "authority.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_osint_lookup_in_ask_for(self):
        a = self._load_authority()
        self.assertIn("osint_lookup:external_target", a["ask_for"])

    def test_self_audit_not_blocked(self):
        a = self._load_authority()
        # osint_lookup (sans :external_target) ne doit pas être dans denylist
        self.assertNotIn("osint_lookup", a.get("denylist", []))


# ═══════════════════════════════════════════════════════════════════════════════
# D) Pipeline intégration end-to-end (moteur mocké)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineIntegration(unittest.TestCase):
    """Teste le pipeline complet engine → rapport avec connecteurs mockés."""

    def _run_engine(self, target_raw, connector_result, mode="self_audit"):
        """Lance lookup_async avec un seul connecteur mocké + guard mockée (ALLOW)."""
        from agent.osint.engine import OSINTEngine
        from agent.osint.safety import LegalCheck, LegalDecision
        from agent.osint.target import TargetNormalizer

        # Connecteur mock
        mock_conn = MagicMock()
        mock_conn.name = "mock_conn"
        mock_conn.supports = {TargetNormalizer.detect(target_raw).type}
        mock_conn.is_available.return_value = True
        mock_conn.query = AsyncMock(return_value=connector_result)

        mock_registry = MagicMock()
        mock_registry.for_target.return_value = [mock_conn]

        # Guard mock → toujours ALLOW
        mock_guard = MagicMock()
        mock_guard.check.return_value = LegalCheck(
            LegalDecision.ALLOW, "test", mode, is_self=True
        )

        mock_ui = MagicMock()
        mock_audit = MagicMock()

        engine = OSINTEngine(ui_bridge=mock_ui, audit_logger=mock_audit)
        engine.guard = mock_guard

        import asyncio
        with patch("agent.osint.engine.get_registry", return_value=mock_registry):
            report = asyncio.run(engine.lookup_async(
                target_raw, mode=mode, consent_id="test_consent"
            ))
        return report

    def _finding(self, ftype="breach", source="test", **extracted):
        from agent.osint.connectors.base import Finding
        return Finding(type=ftype, source=source, extracted=extracted or {"x": 1}, confidence=0.9)

    def _ok_result(self, target_raw, findings):
        from agent.osint.connectors.base import ConnectorResult
        from agent.osint.target import TargetNormalizer
        return ConnectorResult(
            connector="mock_conn",
            target=TargetNormalizer.detect(target_raw),
            success=True,
            findings=findings,
            elapsed_ms=10,
        )

    def _fail_result(self, target_raw):
        from agent.osint.connectors.base import ConnectorResult
        from agent.osint.target import TargetNormalizer
        return ConnectorResult(
            connector="mock_conn",
            target=TargetNormalizer.detect(target_raw),
            success=False,
            error="mock error",
            elapsed_ms=5,
        )

    def test_email_self_audit_full_pipeline(self):
        findings = [self._finding("breach", "hibp", breach_name="Adobe")]
        cr = self._ok_result("user@example.com", findings)
        report = self._run_engine("user@example.com", cr)
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].type, "breach")
        self.assertFalse(report.cancelled)
        self.assertIsNone(report.error)

    def test_domain_with_findings(self):
        findings = [
            self._finding("subdomain", "crtsh", subdomain="api.example.com"),
            self._finding("tech_stack", "builtwith", technologies=["WordPress"]),
        ]
        cr = self._ok_result("example.com", findings)
        report = self._run_engine("example.com", cr)
        self.assertEqual(len(report.findings), 2)
        self.assertIn("mock_conn", report.sources_used)

    def test_connector_failure_recorded(self):
        cr = self._fail_result("1.2.3.4")
        report = self._run_engine("1.2.3.4", cr)
        self.assertEqual(len(report.findings), 0)
        self.assertTrue(any(s == "mock_conn" for s, _ in report.sources_failed))

    def test_analyzers_populated(self):
        findings = [self._finding("breach", "hibp", breach_name="X")]
        cr = self._ok_result("user@example.com", findings)
        report = self._run_engine("user@example.com", cr)
        # analyzers dict doit exister (même vide)
        self.assertIsInstance(report.analyzers, dict)

    def test_report_has_timing(self):
        cr = self._ok_result("example.com", [])
        report = self._run_engine("example.com", cr)
        self.assertGreater(report.duration_ms, 0)
        self.assertGreater(report.completed_at, report.started_at)

    def test_cancel_flag_stops_pipeline(self):
        import asyncio
        from agent.osint.engine import OSINTEngine
        from agent.osint.safety import LegalCheck, LegalDecision
        from agent.osint.target import TargetNormalizer

        async def _slow_query(_):
            await asyncio.sleep(5)
            from agent.osint.connectors.base import ConnectorResult
            return ConnectorResult(connector="slow", target=_, success=True, findings=[], elapsed_ms=5000)

        mock_conn = MagicMock()
        mock_conn.name = "slow"
        mock_conn.supports = {TargetNormalizer.detect("example.com").type}
        mock_conn.is_available.return_value = True
        mock_conn.query = _slow_query

        mock_registry = MagicMock()
        mock_registry.for_target.return_value = [mock_conn]

        mock_guard = MagicMock()
        mock_guard.check.return_value = LegalCheck(
            LegalDecision.ALLOW, "test", "self_audit", is_self=True
        )

        engine = OSINTEngine(ui_bridge=MagicMock(), audit_logger=MagicMock())
        engine.guard = mock_guard

        async def _run():
            engine.cancel()  # flag set avant même de démarrer
            return await engine.lookup_async("example.com", reset_cancel=False)

        with patch("agent.osint.engine.get_registry", return_value=mock_registry):
            report = asyncio.run(_run())
        self.assertTrue(report.cancelled)


# ═══════════════════════════════════════════════════════════════════════════════

def _run_all():
    suite = unittest.TestSuite()
    for cls in [TestOSINTWizard, TestOSINTLookupAction, TestAuthorityConfig, TestPipelineIntegration]:
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w"))
    result = runner.run(suite)

    total = result.testsRun
    fails = len(result.failures) + len(result.errors)

    for test, tb in result.failures + result.errors:
        print(f"  [FAIL] {test}")
        print("   ", tb.splitlines()[-1])

    for test, _ in [(t, None) for t in suite]:
        pass

    # Print per-test OK
    all_tests = []
    for cls in [TestOSINTWizard, TestOSINTLookupAction, TestAuthorityConfig, TestPipelineIntegration]:
        for name in unittest.TestLoader().getTestCaseNames(cls):
            all_tests.append((cls, name))

    failed_names = {str(t) for t, _ in result.failures + result.errors}
    for cls, name in all_tests:
        label = f"{cls.__name__}.{name}"
        status = "FAIL" if any(label in fn for fn in failed_names) else "OK"
        print(f"  [{status}] {name}")

    print(f"\n[RESULTS] Session 6 OSINT -- {total - fails}/{total} passed {'OK' if fails == 0 else 'WITH FAILURES'}")
    return fails == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
