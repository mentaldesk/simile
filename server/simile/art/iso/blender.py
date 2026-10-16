"""Runs a script in Blender as a subprocess: Blender is a tool on the machine, not a dependency."""

import json
import os
import shutil
import subprocess
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent / "in_blender"
SERVER = Path(__file__).resolve().parents[3]
MAC_APP = Path("/Applications/Blender.app/Contents/MacOS/Blender")
PROGRESS = "ISO "
ATTEMPTS = 3


class BlenderError(RuntimeError):
    pass


def find() -> str | None:
    """Blender's executable: $BLENDER, then `blender` on the PATH, then the macOS app."""
    if path := os.environ.get("BLENDER"):
        return path
    if path := shutil.which("blender"):
        return path
    return str(MAC_APP) if MAC_APP.exists() else None


def available() -> bool:
    return find() is not None


def run(
    script: str,
    job: dict[str, Any],
    work: Path,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run `in_blender/<script>` on a job; it writes into `work` and returns its result JSON."""
    blender = find()
    if blender is None:
        raise BlenderError("Blender not found: install it or set $BLENDER")
    work.mkdir(parents=True, exist_ok=True)
    job_path, result_path = work / "job.json", work / "result.json"
    job_path.write_text(json.dumps({**job, "out": str(work), "server": str(SERVER)}))
    result_path.unlink(missing_ok=True)
    command = [
        blender,
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(SCRIPTS / script),
        "--",
        str(job_path),
        str(result_path),
    ]
    for attempt in range(ATTEMPTS):
        code, tail = _blender(command, progress)
        # Cycles' Metal kernel cache sometimes aborts Blender (NSInvalidArgumentException).
        if code >= 0 or attempt == ATTEMPTS - 1:
            break
        progress(f"Blender crashed ({code}); running it again")
    if code != 0 or not result_path.exists():
        raise BlenderError(f"{script} failed ({code}):\n" + "\n".join(tail))
    return json.loads(result_path.read_text())


def _blender(command: list[str], progress: Callable[[str], None]) -> tuple[int, deque[str]]:
    tail: deque[str] = deque(maxlen=40)
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            tail.append(line.rstrip())
            if line.startswith(PROGRESS):
                progress(line[len(PROGRESS) :].rstrip())
    return proc.returncode, tail
