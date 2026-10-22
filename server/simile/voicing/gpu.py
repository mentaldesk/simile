import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

PATTERNS = ("mflux", "simile (papercraft|dolls)")
SHELLS = {"sh", "bash", "zsh", "fish", "sleep", "pgrep", "grep"}
"""Programs whose command lines may mention mflux without running it."""
POLL = 60.0


def busy() -> list[str]:
    """Other image or language models running on this Mac: mflux, a simile build, or Ollama."""
    found = []
    for pattern in PATTERNS:
        try:
            run = subprocess.run(["pgrep", "-fl", pattern], capture_output=True, text=True)
        except FileNotFoundError:
            continue
        for line in run.stdout.splitlines():
            pid, _, command = line.partition(" ")
            if pid != str(os.getpid()) and Path(command.split(" ", 1)[0]).name not in SHELLS:
                found.append(line)
    try:
        ollama = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return found
    return found + [f"ollama: {line}" for line in ollama.splitlines()[1:] if line.strip()]


def wait_for_gpu(say: Callable[[str], object] = print, poll: float = POLL) -> None:
    """Waits until no other model is loaded, so two never share the GPU's memory."""
    while others := busy():
        say(f"Waiting for {'; '.join(others)}")
        time.sleep(poll)
