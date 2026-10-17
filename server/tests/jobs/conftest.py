import asyncio
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from simile.jobs import Kind, url

FAKE_TOOL = Path(__file__).with_name("fake_tool.py")
TIMEOUT = 15.0


class Fake(BaseModel):
    name: str = "out"
    hold: str | None = None
    pid: str | None = None
    child: str | None = None
    stubborn: bool = False
    noise: list[str] = []
    exit: int = 0


def fake_kind(
    name: str = "fake",
    requires: tuple[str, ...] = (),
    command: Callable[[Fake, Path], Sequence[str]] | None = None,
) -> Kind[Fake]:
    def publish(fake: Fake, work: Path, out: Path) -> dict[str, Any]:
        os.replace(work / f"{fake.name}.txt", out / f"{fake.name}.txt")
        return {"file": url(name, f"{fake.name}.txt")}

    def run_fake_tool(fake: Fake, work: Path) -> list[str]:
        return [sys.executable, str(FAKE_TOOL), str(work)]

    return Kind(name, Fake, command or run_fake_tool, publish, requires, files=r"[a-z]+\.txt")


async def until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        await asyncio.sleep(0.01)


def eventually(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    ps = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return ps.stdout.strip().startswith("Z")


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "jobs"
    monkeypatch.setenv("SIMILE_JOBS", str(root))
    return root
