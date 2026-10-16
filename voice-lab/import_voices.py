import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from npcs import (
    clip_path,
    has_voice,
    imported_voices,
    load_npcs,
    measure_rates,
    misheard,
    remove_voice,
    save_imported,
    set_reference_clip,
    word_error_rate,
)

HERE = Path(__file__).parent
INCOMING = HERE / "incoming"
OUT = HERE / "out" / "import"
AUDIO = (".wav", ".mp3", ".m4a")
SAMPLE_RATE = 24_000
MIN_SECONDS, MAX_SECONDS = 5.0, 25.0
MIN_WORDS, MAX_WORDS = 12, 25  # N1's bounds on a reference line, which make test checks
NORTH_AMERICAN = ("us", "canada")


class ConversionError(Exception):
    pass


class Tools(Protocol):
    def convert(self, source: Path, wav: Path) -> None: ...
    def transcribe(self, wav: Path) -> str: ...
    def clone(self, wav: Path, transcript: str, out: Path) -> list[Path]: ...
    def accents(self, wavs: list[Path]) -> dict[str, str]: ...
    def speak(self, npc_ids: list[str]) -> None: ...
    def measure(self, npc_ids: list[str]) -> None: ...


def convert(source: Path, wav: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.wav"
        result = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", f"LEI16@{SAMPLE_RATE}", "-c", "1", source, raw],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ConversionError(result.stderr.strip() or f"afconvert exited with {result.returncode}")
        # afconvert writes WAVE_FORMAT_EXTENSIBLE; write plain PCM like design_npcs.py's clips.
        with wave.open(str(raw)) as reader, wave.open(str(wav), "wb") as writer:
            writer.setparams(reader.getparams())
            writer.writeframes(reader.readframes(reader.getnframes()))


class Models:
    """The real checks, loading each model the first time it's needed."""

    def __init__(self, torch_python: Path) -> None:
        self.torch_python = torch_python
        self.whisper = self.tts = None

    def convert(self, source: Path, wav: Path) -> None:
        convert(source, wav)

    def transcribe(self, wav: Path) -> str:
        import transcribe as stt

        if self.whisper is None:
            self.whisper = stt.load()
        return stt.transcribe(self.whisper, str(wav))

    def clone(self, wav: Path, transcript: str, out: Path) -> list[Path]:
        from clone_accent_test import clone

        if self.tts is None:
            from mlx_audio.tts.utils import load_model

            from speak_npcs import MODEL

            self.tts = load_model(MODEL)
        return clone(self.tts, wav, transcript, out)

    def accents(self, wavs: list[Path]) -> dict[str, str]:
        from clone_accent_test import accents

        return accents(wavs, self.torch_python)

    def speak(self, npc_ids: list[str]) -> None:
        run = [sys.executable, HERE / "speak_npcs.py", *npc_ids, "--force", "--torch-python", self.torch_python]
        subprocess.run(run, check=True)

    def measure(self, npc_ids: list[str]) -> None:
        measure_rates(npc_ids)


@dataclass
class Clip:
    npc_id: str
    source: Path
    transcript: str
    digest: str
    reference_line_changes: bool
    wav: Path | None = None
    seconds: float | None = None
    heard: str | None = None
    word_error_rate: float | None = None
    accent: str | None = None
    samples: list[Path] = field(default_factory=list)
    sample_accents: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = ""


def gather(
    folder: Path, residents: dict[str, dict], only: set[str] | None, force: bool
) -> tuple[list[Clip], list[str]]:
    """The clips in the folder to check, and notes on every file that isn't one."""
    notes, sources, transcripts = [], {}, {}
    for path in sorted(folder.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        if path.suffix.lower() == ".txt":
            transcripts[path.stem] = path
        elif path.suffix.lower() in AUDIO:
            sources.setdefault(path.stem, []).append(path)
        else:
            notes.append(f"Ignored {path.name}: clips must be .wav, .mp3 or .m4a")
    if unknown := sorted((sources.keys() | transcripts.keys()) - residents.keys()):
        for stem in unknown:
            names = [path.name for path in sources.get(stem, [])] + ([f"{stem}.txt"] if stem in transcripts else [])
            notes.append(f"Unknown resident {stem!r}: {', '.join(names)}")
        notes.append(f"Name each clip and transcript after a resident: {', '.join(residents)}")

    imported, clips, no_clip = imported_voices(), [], []
    for npc_id, npc in residents.items():
        if only and npc_id not in only:
            continue
        found = sources.get(npc_id, [])
        if not found:
            if only or npc_id in transcripts:
                no_clip.append(npc_id)
        elif len(found) > 1:
            notes.append(f"{npc_id}: {' and '.join(path.name for path in found)} are both clips for them. Keep one")
        elif npc_id not in transcripts:
            notes.append(f"{npc_id}: no transcript. Add {npc_id}.txt with exactly what {found[0].name} says")
        else:
            transcript = " ".join(transcripts[npc_id].read_text(encoding="utf-8-sig").split())
            digest = hashlib.sha256(found[0].read_bytes() + transcript.encode()).hexdigest()
            line = npc["voice"]["reference_line"]
            if not force and imported.get(npc_id) == digest and has_voice(npc_id, npc) and line == transcript:
                notes.append(f"{npc_id}: already imported from {found[0].name}. --force imports it again")
                continue
            clips.append(Clip(npc_id, found[0], transcript, digest, reference_line_changes=line != transcript))
    if no_clip:
        notes.append(f"No clip for {', '.join(no_clip)}: left alone")
    return clips, notes


def check(clips: list[Clip], tools: Tools, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for clip in clips:
        count = len(clip.transcript.split())
        if not MIN_WORDS <= count <= MAX_WORDS:
            clip.errors.append(
                f"the transcript is {count} words, but a reference line is {MIN_WORDS}-{MAX_WORDS}: "
                "trim the clip and transcript to a sentence or two"
            )
        if "!" in clip.transcript:
            clip.errors.append("the transcript has a '!', but reference lines stay neutral: end it with '.'")
        clip.wav = out / f"{clip.npc_id}.wav"
        try:
            tools.convert(clip.source, clip.wav)
        except ConversionError as error:
            clip.errors.append(f"couldn't convert {clip.source.name}: {error}")
            continue
        clip.wav.with_suffix(".txt").write_text(clip.transcript + "\n", encoding="utf-8")
        with wave.open(str(clip.wav)) as reader:
            clip.seconds = reader.getnframes() / reader.getframerate()
        if not MIN_SECONDS <= clip.seconds <= MAX_SECONDS:
            clip.problems.append(f"{clip.seconds:.1f} s long, not {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f} s")

    todo = [clip for clip in clips if not clip.errors]
    for clip in todo:
        print(f"Checking {clip.npc_id}'s clip")
        clip.heard = tools.transcribe(clip.wav)
        clip.word_error_rate = word_error_rate(clip.transcript, clip.heard)
        clip.problems += misheard(clip.transcript, clip.heard)
        clip.samples = tools.clone(clip.wav, clip.transcript, out / "samples")
    if not todo:
        return
    heard = tools.accents([path for clip in todo for path in (clip.wav, *clip.samples)])
    for clip in todo:
        clip.accent = heard[str(clip.wav)]
        clip.sample_accents = [heard[str(path)] for path in clip.samples]
        named = [("the clip", clip.accent), *((f"sample {n}", a) for n, a in enumerate(clip.sample_accents, 1))]
        for name, accent in named:
            if accent.split()[0] in NORTH_AMERICAN:
                clip.warnings.append(f"{name} sounds North American ({accent})")


def install(clip: Clip) -> None:
    remove_voice(clip.npc_id)
    target = clip_path(clip.npc_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip.wav, target)
    target.with_suffix(".txt").write_text(clip.transcript + "\n", encoding="utf-8")
    set_reference_clip(clip.npc_id, target, clip.transcript)


def report(clip: Clip) -> str:
    lines = [f"{clip.npc_id} ({clip.source.name}): {clip.status}"]
    if clip.seconds is not None:
        lines.append(f"  length: {clip.seconds:.1f} s")
    if clip.heard is not None:
        lines.append(f"  Whisper heard: {clip.heard}")
        lines.append(f"  word error rate: {clip.word_error_rate:.0%}")
    lines.append(f"  reference line: {'becomes the transcript' if clip.reference_line_changes else 'unchanged'}")
    if clip.accent is not None:
        lines.append(f"  accent of the clip: {clip.accent}")
        lines.append(f"  accent of its samples: {' · '.join(clip.sample_accents)}")
    lines += [f"  can't import: {error}" for error in clip.errors]
    lines += [f"  problem: {problem}" for problem in clip.problems]
    lines += [f"  warning: {warning}" for warning in clip.warnings]
    return "\n".join(lines)


def run(
    folder: Path,
    tools: Tools,
    dry_run: bool = False,
    force: bool = False,
    only: set[str] | None = None,
    out: Path = OUT,
) -> list[Clip]:
    residents = load_npcs()
    if unknown := (only or set()) - residents.keys():
        raise SystemExit(f"no such resident: {', '.join(sorted(unknown))}")
    clips, notes = gather(folder, residents, only, force)
    if notes:
        print("\n".join(notes))
    if not clips:
        print(f"Nothing to import from {folder}.")
        return clips

    check(clips, tools, out)
    for clip in clips:
        if clip.errors:
            clip.status = "can't import"
        elif clip.problems and not force:
            clip.status = "not imported: --force imports it anyway"
        else:
            clip.status = "would import" if dry_run else "imported"
    todo = [clip for clip in clips if clip.status == "imported"]
    failed = []
    if todo:
        imported = imported_voices()
        for clip in todo:
            install(clip)
            imported[clip.npc_id] = clip.digest
        save_imported(imported)
        ids = [clip.npc_id for clip in todo]
        print(f"\nSpeaking the samples of {', '.join(ids)} with speak_npcs.py", flush=True)
        try:
            tools.speak(ids)
        except subprocess.CalledProcessError:
            failed.append(f"speak_npcs.py failed, so rerun it: .venv-mlx/bin/python speak_npcs.py {' '.join(ids)} --force")
        print(f"\nMeasuring how fast {', '.join(ids)} speak", flush=True)
        try:
            tools.measure(ids)
        except (OSError, subprocess.CalledProcessError):
            failed.append(f"Measuring failed, so rerun it: cd ../server && uv run --extra voice simile voice measure {' '.join(ids)}")

    print()
    print("\n\n".join(map(report, clips)))
    print(f"\nTo listen: the converted clips and the samples cloned from them are in {out}")
    if failed:
        raise SystemExit("\n".join(failed))
    return clips


def write_scripts(folder: Path, only: set[str] | None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for npc_id, npc in load_npcs(sorted(only) if only else None).items():
        path = folder / f"{npc_id}.txt"
        if path.exists():
            print(f"Kept {path.name}")
        else:
            path.write_text(npc["voice"]["reference_line"] + "\n", encoding="utf-8")
            print(f"Wrote {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a recorded reference clip and its transcript per resident.")
    parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        default=INCOMING,
        help="holds <id>.wav, .mp3 or .m4a with <id>.txt, its exact transcript (default: incoming/)",
    )
    parser.add_argument("--dry-run", action="store_true", help="check every clip but change nothing")
    parser.add_argument(
        "--force", action="store_true", help="import despite length or word error rate problems, or reimport"
    )
    parser.add_argument("--only", type=lambda ids: set(filter(None, ids.split(","))), help="resident ids, a,b,c")
    parser.add_argument(
        "--scripts", action="store_true", help="write each resident's reference line to <id>.txt to record, and stop"
    )
    parser.add_argument("--torch-python", type=Path, default=HERE / ".venv" / "bin" / "python")
    args = parser.parse_args()

    if args.scripts:
        write_scripts(args.folder, args.only)
        return
    if not args.folder.is_dir():
        raise SystemExit(f"{args.folder} doesn't exist. --scripts creates it with a transcript for each resident")
    run(args.folder, Models(args.torch_python), args.dry_run, args.force, args.only)


if __name__ == "__main__":
    main()
