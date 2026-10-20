"""What this machine can run, checked once when the server starts."""

import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

VOICE_LAB = Path(__file__).resolve().parents[3] / "voice-lab"


@dataclass(frozen=True)
class Capability:
    name: str
    needs: str
    check: Callable[[], bool]


def apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def venv(name: str) -> Callable[[], bool]:
    return lambda: (VOICE_LAB / name / "bin" / "python").exists()


CAPABILITIES = {
    c.name: c
    for c in (
        Capability("apple_silicon", "a Mac with Apple Silicon", apple_silicon),
        Capability("voice_lab", "voice-lab/.venv (see voice-lab/README.md)", venv(".venv")),
        Capability(
            "voice_lab_mlx", "voice-lab/.venv-mlx (see voice-lab/README.md)", venv(".venv-mlx")
        ),
    )
}


def detect() -> dict[str, bool]:
    return {name: capability.check() for name, capability in CAPABILITIES.items()}


def needs(name: str) -> str:
    return CAPABILITIES[name].needs if name in CAPABILITIES else name
