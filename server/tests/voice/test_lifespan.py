import logging
import sys
import types

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.voice import FakeSynthesiser, VoiceService, voice_of


@pytest.fixture
def qwen(monkeypatch: pytest.MonkeyPatch, synthesiser: FakeSynthesiser) -> FakeSynthesiser:
    module = types.ModuleType("simile.voice.qwen")
    module.QwenSynthesiser = lambda: synthesiser  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "simile.voice.qwen", module)
    monkeypatch.setenv("SIMILE_VOICE", "1")
    return synthesiser


def test_runs_unvoiced_unless_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_VOICE", raising=False)
    app = create_app()

    with TestClient(app):
        assert voice_of(app) is None


def test_loads_the_voice_model_when_asked(qwen: FakeSynthesiser) -> None:
    app = create_app()

    with TestClient(app):
        assert isinstance(voice_of(app), VoiceService)
        assert qwen.loaded


def test_runs_unvoiced_headless(qwen: FakeSynthesiser) -> None:
    app = create_app()
    app.state.headless = True

    with TestClient(app):
        assert voice_of(app) is None
    assert not qwen.loaded


def test_runs_unvoiced_without_the_voice_extra(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SIMILE_VOICE", "1")
    monkeypatch.setitem(sys.modules, "simile.voice.qwen", None)
    app = create_app()

    with caplog.at_level(logging.WARNING), TestClient(app):
        assert voice_of(app) is None
    assert "voice extra isn't installed" in caplog.text
