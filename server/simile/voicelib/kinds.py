"""The voice jobs, which run `voice-lab/voice_job.py` in voice-lab's virtualenvs."""

import os
import secrets
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, Field
from pydantic_core import PydanticCustomError

from simile.jobs import Jobs, Kind, url
from simile.jobs.capabilities import VOICE_LAB
from simile.library import Refused
from simile.schema import Model

SCRIPT = VOICE_LAB / "voice_job.py"
TORCH_PYTHON = VOICE_LAB / ".venv" / "bin" / "python"
MLX_PYTHON = VOICE_LAB / ".venv-mlx" / "bin" / "python"
NEEDS = ("apple_silicon", "voice_lab", "voice_lab_mlx")
DESIGN, CHECK = "voice_design", "voice_check"
JOB = r"[0-9a-f]{16}"
UPLOAD = r"^[0-9a-f]{32}\.(wav|mp3|m4a)$"
MAX_CANDIDATES = 6
KEEP = 20


class Missing(LookupError):
    pass


def _spoken(text: str) -> str:
    if not (text := " ".join(text.split())):
        raise PydanticCustomError("blank", "can't be blank")
    return text


Spoken = Annotated[str, AfterValidator(_spoken)]


class VoiceDesign(Model):
    description: Spoken = Field(max_length=600)
    reference_line: Spoken = Field(max_length=400)
    count: int = Field(default=4, ge=1, le=MAX_CANDIDATES)
    seed: int = Field(default_factory=lambda: secrets.randbelow(2**31), ge=0, lt=2**31)


class VoiceCheck(Model):
    upload: str = Field(pattern=UPLOAD)
    reference_line: Spoken = Field(max_length=400)


class Candidate(Model):
    seconds: float
    heard: str
    word_error_rate: float
    accent: str
    clone_accent: str
    problems: list[str]
    warnings: list[str]


class PublishedCandidate(Candidate):
    n: int
    clip: str
    clone: str


class Published(Model):
    description: str
    reference_line: str
    seed: int
    candidates: list[PublishedCandidate]


class Checks(Model):
    seconds: float | None
    heard: str | None
    word_error_rate: float | None
    accent: str | None
    sample_accents: list[str]
    errors: list[str]
    problems: list[str]
    warnings: list[str]


class Checked(Checks):
    reference_line: str
    clip: str | None
    samples: list[str]
    usable: bool


class Found(Model):
    candidates: list[Candidate]


def uploads_dir(root: Path) -> Path:
    return root / CHECK / "uploads"


def design_command(params: VoiceDesign, work: Path) -> list[str]:
    return [str(TORCH_PYTHON), str(SCRIPT), "design", str(work)]


def check_command(params: VoiceCheck, work: Path) -> list[str]:
    upload = uploads_dir(work.parents[1]) / params.upload
    return [str(MLX_PYTHON), str(SCRIPT), "check", str(work), str(upload)]


def publish_design(params: VoiceDesign, work: Path, out: Path) -> dict[str, Any]:
    job = work.name
    found = Found.model_validate_json((work / "result.json").read_bytes())
    candidates = []
    for n, candidate in enumerate(found.candidates, 1):
        clip, clone = f"{job}_{n}.wav", f"{job}_{n}_clone.wav"
        os.replace(work / f"candidate_{n}.wav", out / clip)
        os.replace(work / f"candidate_{n}_1.wav", out / clone)
        published = {"n": n, "clip": url(DESIGN, clip), "clone": url(DESIGN, clone)}
        candidates.append(PublishedCandidate(**candidate.model_dump(), **published))
    result = Published(
        description=params.description,
        reference_line=params.reference_line,
        seed=params.seed,
        candidates=candidates,
    )
    return _manifest(out, job, result)


def publish_check(params: VoiceCheck, work: Path, out: Path) -> dict[str, Any]:
    job = work.name
    checks = Checks.model_validate_json((work / "result.json").read_bytes())
    clip = None
    if not checks.errors and (work / "recording.wav").is_file():
        os.replace(work / "recording.wav", out / f"{job}.wav")
        clip = url(CHECK, f"{job}.wav")
    samples = []
    for n, sample in enumerate(sorted((work / "samples").glob("recording_*.wav")), 1):
        os.replace(sample, out / f"{job}_{n}.wav")
        samples.append(url(CHECK, f"{job}_{n}.wav"))
    result = Checked(
        **checks.model_dump(),
        reference_line=params.reference_line,
        clip=clip,
        samples=samples,
        usable=clip is not None and not checks.errors and not checks.problems,
    )
    return _manifest(out, job, result)


def _manifest(out: Path, job: str, result: Model) -> dict[str, Any]:
    (out / f"{job}.json").write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    manifests = sorted(out.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in manifests[KEEP:]:
        for path in out.glob(f"{old.stem}*"):
            path.unlink(missing_ok=True)
    return result.model_dump(mode="json")


DESIGN_KIND = Kind(
    DESIGN,
    VoiceDesign,
    design_command,
    publish_design,
    NEEDS,
    files=rf"{JOB}(_[1-{MAX_CANDIDATES}](_clone)?)?\.(wav|json)",
)
CHECK_KIND = Kind(
    CHECK, VoiceCheck, check_command, publish_check, NEEDS, files=rf"{JOB}(_\d)?\.(wav|json)"
)


def designed(jobs: Jobs, job: str, candidate: int) -> tuple[bytes, str]:
    """A design job's candidate clip and what it says."""
    manifest = jobs.file(DESIGN, f"{job}.json")
    if manifest is None:
        raise Missing("Those designed voices are gone, so design them again")
    result = Published.model_validate_json(manifest.read_bytes())
    clip = jobs.file(DESIGN, f"{job}_{candidate}.wav")
    if candidate > len(result.candidates) or clip is None:
        raise Missing(f"That design has no voice {candidate}")
    return clip.read_bytes(), result.reference_line


def recorded(jobs: Jobs, job: str) -> tuple[bytes, str]:
    """A checked recording and what it says, if it passed its checks."""
    manifest = jobs.file(CHECK, f"{job}.json")
    if manifest is None:
        raise Missing("That recording is gone, so record it again")
    result = Checked.model_validate_json(manifest.read_bytes())
    clip = jobs.file(CHECK, f"{job}.wav")
    if not result.usable or clip is None:
        reasons = "; ".join(result.errors + result.problems) or "it didn't convert"
        raise Refused(f"The recording didn't pass its checks: {reasons}")
    return clip.read_bytes(), result.reference_line
