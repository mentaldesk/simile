"""Stands in for `simile/voicing/speak.py` as the greetings job runs it, without the voice model."""

import json
import sys
from pathlib import Path

work = Path(sys.argv[1])
asked = json.loads((work / "greetings.json").read_text())
for n, line in enumerate(asked["lines"], 1):
    print("JOB " + json.dumps({"progress": n / 5, "message": f"Saying greeting {n}"}), flush=True)
    (work / f"{asked['voice']}_{n}.m4a").write_text(f"{line} in {Path(asked['clip']).name}")
seconds = [1.0 + n / 10 for n in range(len(asked["lines"]))]
(work / "spoken.json").write_text(json.dumps({"seconds": seconds}))
