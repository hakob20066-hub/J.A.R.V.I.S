"""Regression tests for cloud-only mode and VoiceFast provider routing."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_ollama_unavailable_when_local_llm_disabled():
    from agent.llm_router import LLMRouter

    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp) / "runtime.json"
        runtime.write_text(json.dumps({"local_llm_enabled": False}), encoding="utf-8")

        with patch("agent.llm_router.RUNTIME_PATH", runtime):
            router = LLMRouter(chain=["ollama"])
            router.cfg = {}

            assert router.is_provider_usable("ollama") is False


def test_voice_fast_skips_unusable_fast_providers_before_fallback():
    from agent.voices.voice_fast import VoiceFast

    fake_router = MagicMock()
    fake_router.is_provider_usable.side_effect = lambda provider: provider == "mistral"
    fake_router.generate.return_value = "Bonjour."
    fake_router.last_provider = "mistral"

    with patch("agent.llm_router.get_router", return_value=fake_router):
        resp = VoiceFast().process("Salut")

    assert resp.provider_used == "mistral"
    assert resp.text == "Bonjour."
    assert fake_router.generate.call_count == 1
    assert fake_router.generate.call_args.kwargs["model"] == "mistral-large-latest"


def test_wizard_ttft_reports_error_provider_as_not_ok():
    from ui_wizard import WizardApi
    from agent.voices.base import VoiceResponse

    api = WizardApi()
    error_response = VoiceResponse(
        text="[VoiceFast error] All providers failed.",
        voice_id=4,
        provider_used="error",
    )

    fake_voice = MagicMock()
    fake_voice.process.return_value = error_response
    with patch("ui_wizard._get_voice", return_value=fake_voice):
        result = api.run_ttft_test("hello")

    assert result["ok"] is False
    assert result["provider"] == "error"


def test_legacy_ollama_model_names_are_normalized():
    from agent.local_llm_provider import normalize_model_name

    assert normalize_model_name("llama3.2-3b-instruct-abliterated") == "llama3.2:3b"
    assert normalize_model_name("qwen2.5-abliterate:14b") == "qwen2.5:14b"


def test_ollama_progress_output_is_cleaned():
    from agent.local_llm_provider import _clean_ollama_output

    assert _clean_ollama_output("\x1b[?2026h\x1b[1Gpulling manifest \r") == "pulling manifest"
