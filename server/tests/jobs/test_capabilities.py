from pathlib import Path
from types import SimpleNamespace

import pytest

from simile.jobs import capabilities
from simile.jobs.capabilities import detect


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(capabilities, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(capabilities, "platform", SimpleNamespace(machine=lambda: "arm64"))
    monkeypatch.setattr(capabilities, "VOICE_LAB", tmp_path / "voice-lab")
    return tmp_path


def test_finds_what_this_machine_has(machine: Path) -> None:
    for venv in (".venv", ".venv-mlx"):
        (machine / "voice-lab" / venv / "bin").mkdir(parents=True)
        (machine / "voice-lab" / venv / "bin" / "python").touch()

    assert detect() == {"apple_silicon": True, "voice_lab": True, "voice_lab_mlx": True}


def test_finds_what_this_machine_lacks(machine: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capabilities, "platform", SimpleNamespace(machine=lambda: "x86_64"))
    (machine / "voice-lab" / ".venv-mlx" / "bin").mkdir(parents=True)
    (machine / "voice-lab" / ".venv-mlx" / "bin" / "python").touch()

    assert detect() == {"apple_silicon": False, "voice_lab": False, "voice_lab_mlx": True}


def test_linux_isnt_apple_silicon(machine: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capabilities, "sys", SimpleNamespace(platform="linux"))

    assert detect()["apple_silicon"] is False
