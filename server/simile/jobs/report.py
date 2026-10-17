"""What a job's subprocess prints so the runner can follow it."""

import json

PREFIX = "JOB "


def progress(fraction: float, message: str = "") -> None:
    print(PREFIX + json.dumps({"progress": fraction, "message": message}), flush=True)
