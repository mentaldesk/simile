"""A stand-in for a slow tool, run as a job's subprocess: `python fake_tool.py <work>`."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def report(progress: float, message: str) -> None:
    print("JOB " + json.dumps({"progress": progress, "message": message}), flush=True)


def wait_for(path: str) -> None:
    while not Path(path).exists():
        time.sleep(0.01)


def main(work: Path) -> int:
    params = json.loads((work / "params.json").read_text())
    if params["stubborn"]:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if params["child"]:
        output = subprocess.DEVNULL if params["detach"] else None
        sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
        child = subprocess.Popen(sleeper, stdout=output, stderr=output)
        Path(params["child"]).write_text(str(child.pid))
    for line in params["noise"]:
        print(line, flush=True)
    report(0.5, "Halfway")
    if params["pid"]:
        Path(params["pid"]).write_text(str(os.getpid()))
    if params["hold"]:
        wait_for(params["hold"])
    report(1.0, "Done")
    (work / f"{params['name']}.txt").write_text(params["name"])
    return params["exit"]


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
