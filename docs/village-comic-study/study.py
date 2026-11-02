"""Paths, the two line treatments, the reference sets, the GPU check and the timing log."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

STUDY = Path(__file__).resolve().parent
DOCS = STUDY.parent
OUT = STUDY / "out"
IMAGES = STUDY / "images"
STUDY2 = DOCS / "style-study-2"
CONTENT = DOCS.parent / "content"

TAG = "simile papercraft"
"""Passed on every painting run's command line, so other builds' GPU checks wait for this one."""
OTHERS = ("mflux", "simile (icons|dolls|papercraft|creatures)")
SHELLS = {"sh", "bash", "zsh", "fish", "sleep", "pgrep", "grep", "ps"}


def study2(name: str):
    """A module of #329's study, by file, so its `common` doesn't meet this study's modules."""
    if str(STUDY2) not in sys.path:
        sys.path.append(str(STUDY2))
    spec = importlib.util.spec_from_file_location(f"study2_{name}", STUDY2 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Line:
    """A line treatment: the style words every prompt ends with, and its redraw words."""

    name: str
    called: str
    look: str
    made: str
    finish: str
    whole: str


SMOOTH = Line(
    "a",
    "clean cartoon",
    "hand-drawn 2D cartoon game art: smooth, even dark brown ink outlines of one steady weight, "
    "flat colour fills with simple soft shading, clean surfaces with no smudges, stains or "
    "grime, chunky rounded simplified shapes, bold readable silhouettes",
    "hand-drawn in the clean cartoon style",
    "smooth, even dark ink outlines of one steady weight around every shape, flat colours with "
    "simple soft shading, and clean surfaces",
    "Everything in the picture, the buildings, the glass towers, the trees, the vehicles and the "
    "people, is drawn as a clean chunky cartoon with smooth, even dark ink outlines of one steady "
    "weight and clean surfaces, and the people have very big round heads on small bodies.",
)
"""A: the figures' line (`simile.dolls.figure.LOOK`), with its clean words."""
SCRATCHY = Line(
    "b",
    "scratchy cartoon",
    "hand-drawn 2D cartoon game art: thick dark brown ink outlines that are scratchy, uneven and "
    "slightly broken, as if drawn with a worn dip pen, flat colour fills with simple soft "
    "shading, chunky rounded simplified shapes, bold readable silhouettes",
    "hand-drawn in the scratchy cartoon style",
    "thick scratchy, uneven dark ink outlines around every shape and flat colours with simple "
    "soft shading",
    "Everything in the picture, the buildings, the glass towers, the trees, the vehicles and the "
    "people, is drawn as a chunky cartoon with thick scratchy, uneven dark ink lines, and the "
    "people have very big round heads on small bodies.",
)
"""B: the tunnels' line (`simile.papercraft.painter.CARTOON`) without its dirt and muted palette."""
LINES = {line.name: line for line in (SMOOTH, SCRATCHY)}
NO_TEXT = " No text, no lettering, no logos, no words on signs."

REFERENCE_SETS = {
    "new": "village-comic-study/references/{line}",
    "326": "style-study-2/references/cartoon",
}
"""Each set's folder under docs/: the new ones are painted for each line, #326's are shared."""


def styled(subject: str, line: Line) -> str:
    return f"{subject} Art style: {line.look}.{NO_TEXT}"


def ours() -> set[str]:
    """This process and those that started it."""
    found, pid = set(), os.getpid()
    while pid > 1 and str(pid) not in found:
        found.add(str(pid))
        parent = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True)
        pid = int(parent.stdout.strip() or 0)
    return found


def busy() -> list[str]:
    """Other image models on this Mac: mflux, a simile build, or an Ollama model."""
    found, mine = [], ours()
    for pattern in OTHERS:
        run = subprocess.run(["pgrep", "-fl", pattern], capture_output=True, text=True)
        for line in run.stdout.splitlines():
            pid, _, command = line.partition(" ")
            if pid not in mine and Path(command.split(" ", 1)[0]).name not in SHELLS:
                found.append(line)
    try:
        ollama = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        ollama = ""
    return found + [f"ollama: {line}" for line in ollama.splitlines()[1:] if line.strip()]


def wait_for_gpu() -> None:
    while others := busy():
        print(f"Waiting for {others}", flush=True)
        time.sleep(60)


def log(entry: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "timings.jsonl").open("a") as f:
        f.write(json.dumps({"at": round(time.time()), **entry}) + "\n")


def args() -> list[str]:
    """The command line without `TAG`."""
    return [a for a in sys.argv[1:] if a != TAG]
