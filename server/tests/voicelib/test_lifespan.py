import os
import time
from collections.abc import Callable
from pathlib import Path

from starlette.testclient import TestClient

from simile.app import create_app
from simile.jobs import Jobs, jobs_of


def test_registers_the_voice_jobs(
    make_package: Callable[[dict[str, str]], str], tmp_path: Path
) -> None:
    app = create_app(
        make_package(
            {
                "jobs/lifespan.py": "from simile.jobs.lifespan import lifespan\n",
                "jobs/routes.py": "from simile.jobs.routes import routes\n",
                "voicelib/lifespan.py": "from simile.voicelib.lifespan import lifespan\n",
            }
        )
    )
    app.state.jobs = Jobs(
        tmp_path / "jobs", {"apple_silicon": False, "voice_lab": True, "voice_lab_mlx": True}
    )
    uploads = tmp_path / "jobs" / "voice_check" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "old.wav").write_bytes(b"RIFF")
    two_days_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(uploads / "old.wav", (two_days_ago, two_days_ago))

    with TestClient(app) as client:
        kinds = client.get("/api/jobs/capabilities").json()["kinds"]

    reason = "jobs need a Mac with Apple Silicon, which this machine doesn't have"
    assert kinds["voice_design"] == {"available": False, "reason": f"voice_design {reason}"}
    assert kinds["voice_check"] == {"available": False, "reason": f"voice_check {reason}"}
    assert list(uploads.iterdir()) == []
    assert "voice_design" not in jobs_of(app).capabilities()["kinds"]
