"""Tests for setup wizard and auto-optimizer flow."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.hardware_detect import HardwareInfo  # noqa: E402
from ui_wizard import API_FIELDS, WizardApi  # noqa: E402


def test_wizard_exposes_hardware_and_justification():
    with patch("ui_wizard.detect_hardware") as detect:
        detect.return_value = HardwareInfo(
            cpu_name="CPU",
            cpu_cores=8,
            ram_gb=32.0,
            gpu_name="GPU",
            vram_gb=12.0,
            recommended_local_backend="airllm",
            recommended_local_model="qwen2.5-72b-abliterate",
            detection_warnings=[],
            has_gpu=True,
            gpu_vendor="nvidia",
            os="windows",
        )
        api = WizardApi()
        hw = api.get_hardware()
        assert hw["recommended_local_backend"] == "airllm"
        assert "VRAM 12-23GB" in hw["justification"]


def test_wizard_api_schema_has_13_keys():
    api = WizardApi()
    schema = api.get_api_schema()
    assert len(schema) == 13
    assert schema == API_FIELDS


def test_wizard_start_model_install_success():
    api = WizardApi()
    with patch("ui_wizard.ensure_model_installed") as ensure:
        def fake_install(on_progress=None, force_redetect=False):
            if on_progress:
                on_progress(50.0, "mid")
                on_progress(100.0, "done")
        ensure.side_effect = fake_install
        api.start_model_install()
        # worker thread is very short in this mocked case
        import time
        time.sleep(0.05)
        status = api.get_install_status()
        assert status["completed"] is True
        assert status["progress"] == 100.0


def test_wizard_test_api_key_rejects_placeholder():
    api = WizardApi()
    res = api.test_api_key("gemini", "YOUR_GEMINI_API_KEY")
    assert res["ok"] is False


def test_wizard_ttft_uses_voice_router():
    api = WizardApi()
    fake_resp = MagicMock(voice_id=4, provider_used="ollama", text="hello")
    with patch("ui_wizard.voice_process", return_value=fake_resp):
        out = api.run_ttft_test("test")
        assert out["ok"] is True
        assert out["voice_id"] == 4
