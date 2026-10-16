import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

import npcs
from import_voices import SAMPLE_RATE, ConversionError, convert, run, write_scripts

COMMITTED_NPCS = Path(__file__).resolve().parents[2] / "content" / "npcs"
LINES = {
    "desmond": "Kia orana. The form is due on Friday, so bring your letters and we'll go through it together.",
    "priya": "Doors open at eight tonight, and the first round of the new menu is on the house.",
}
NEW_LINE = "Right, so the landlord owes you the bond back, and we'll write to him about it this week."


def resident(npc_id: str, line: str) -> dict:
    return {
        "id": npc_id,
        "name": f"{npc_id.title()} Puna",
        "backstory": "Grew up in Arorangi and keeps up his Cook Islands Māori.",
        "values": {"honesty": 0.86, "pleasure": 0.07},
        "voice": {
            "description": "A heavy Cook Islands accent. A man in his early forties.",
            "reference_line": line,
            "reference_clip": f"content/voices/{npc_id}.wav",
        },
    }


def n1_json(npc: dict) -> str:
    return json.dumps(npc, indent=2, ensure_ascii=False) + "\n"


def write_wav(path: Path, seconds: float, rate: int = SAMPLE_RATE, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(bytes(2 * channels * int(seconds * rate)))


class FakeTools:
    def __init__(self, heard: dict[str, str] | None = None, accents: dict[str, str] | None = None) -> None:
        self.heard = heard or {}
        self.accent = accents or {}
        self.transcribed: list[str] = []
        self.spoken: list[list[str]] = []
        self.measured: list[list[str]] = []

    def convert(self, source: Path, wav: Path) -> None:
        if source.read_bytes()[:4] != b"RIFF":
            raise ConversionError("Couldn't open input file")
        shutil.copyfile(source, wav)

    def transcribe(self, wav: Path) -> str:
        self.transcribed.append(wav.stem)
        return self.heard.get(wav.stem, wav.with_suffix(".txt").read_text())

    def clone(self, wav: Path, transcript: str, out: Path) -> list[Path]:
        out.mkdir(parents=True, exist_ok=True)
        paths = [out / f"{wav.stem}_{n}.wav" for n in (1, 2, 3)]
        for path in paths:
            write_wav(path, 4.0)
        return paths

    def accents(self, wavs: list[Path]) -> dict[str, str]:
        return {str(wav): self.accent.get(wav.stem, "australia 99%") for wav in wavs}

    def speak(self, npc_ids: list[str]) -> None:
        self.spoken.append(npc_ids)

    def measure(self, npc_ids: list[str]) -> None:
        self.measured.append(npc_ids)


@pytest.fixture
def content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setattr(npcs, "REPO_ROOT", root)
    monkeypatch.setattr(npcs, "NPCS", root / "content" / "npcs")
    monkeypatch.setattr(npcs, "VOICES", root / "content" / "voices")
    monkeypatch.setattr(npcs, "SAMPLES", root / "content" / "voices" / "samples")
    npcs.NPCS.mkdir(parents=True)
    npcs.SAMPLES.mkdir(parents=True)
    for npc_id, line in LINES.items():
        (npcs.NPCS / f"{npc_id}.json").write_text(n1_json(resident(npc_id, line)), encoding="utf-8")
        write_wav(npcs.clip_path(npc_id), 7.0)
        npcs.clip_path(npc_id).with_suffix(".txt").write_text(line + "\n")
        for sample in npcs.sample_paths(npc_id):
            sample.write_bytes(b"designed")
    return root / "content"


@pytest.fixture
def incoming(tmp_path: Path) -> Path:
    folder = tmp_path / "incoming"
    folder.mkdir()
    return folder


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "out"


def drop(folder: Path, npc_id: str, seconds: float = 8.0, transcript: str | None = None, suffix: str = ".wav") -> None:
    write_wav(folder / f"{npc_id}{suffix}", seconds)
    (folder / f"{npc_id}.txt").write_text((transcript or LINES[npc_id]) + "\n")


def snapshot(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


def test_imports_a_clip_as_the_residents_voice(content: Path, incoming: Path, out: Path) -> None:
    write_wav(incoming / "desmond.m4a", 8.0)
    (incoming / "desmond.txt").write_text("﻿" + NEW_LINE.replace(", and ", ",\nand  "), encoding="utf-8")
    priya = snapshot(content / "npcs") | {"priya.wav": npcs.clip_path("priya").read_bytes()}
    tools = FakeTools()

    [clip] = run(incoming, tools, out=out)

    assert clip.status == "imported"
    assert npcs.clip_path("desmond").read_bytes() == (out / "desmond.wav").read_bytes()
    assert npcs.clip_path("desmond").with_suffix(".txt").read_text() == NEW_LINE + "\n"
    expected = resident("desmond", NEW_LINE)
    assert (content / "npcs" / "desmond.json").read_text(encoding="utf-8") == n1_json(expected)
    assert not any(path.exists() for path in npcs.sample_paths("desmond"))
    assert tools.spoken == [["desmond"]]
    assert tools.measured == [["desmond"]]
    assert set(npcs.imported_voices()) == {"desmond"}
    assert (content / "npcs" / "priya.json").read_bytes() == priya["priya.json"]
    assert npcs.clip_path("priya").read_bytes() == priya["priya.wav"]


def test_the_reference_line_is_reported_unchanged_when_the_transcript_is_it(
    content: Path, incoming: Path, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drop(incoming, "desmond")

    run(incoming, FakeTools(), out=out)

    assert "reference line: unchanged" in capsys.readouterr().out
    assert json.loads((content / "npcs" / "desmond.json").read_text())["voice"]["reference_line"] == LINES["desmond"]


def test_a_dry_run_checks_but_changes_nothing(
    content: Path, incoming: Path, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drop(incoming, "desmond", transcript=NEW_LINE)
    before = snapshot(content)
    tools = FakeTools()

    [clip] = run(incoming, tools, dry_run=True, out=out)

    assert clip.status == "would import"
    assert tools.transcribed == ["desmond"]
    assert (out / "samples" / "desmond_1.wav").exists()
    assert snapshot(content) == before
    assert tools.spoken == []
    assert "desmond (desmond.wav): would import" in capsys.readouterr().out


@pytest.mark.parametrize(("seconds", "imported"), [(4.9, False), (5.0, True), (25.0, True), (25.1, False)])
def test_a_clip_must_be_5_to_25_seconds(
    content: Path, incoming: Path, out: Path, seconds: float, imported: bool
) -> None:
    drop(incoming, "desmond", seconds)

    [clip] = run(incoming, FakeTools(), out=out)

    assert (clip.status == "imported") == imported
    assert bool(clip.problems) != imported
    assert npcs.imported_voices().keys() == ({"desmond"} if imported else set())


def test_whisper_must_hear_the_transcript(content: Path, incoming: Path, out: Path) -> None:
    drop(incoming, "desmond")
    heard = "Kia orana. The farm is due on Friday, so bring the letter and we'll go through."

    [clip] = run(incoming, FakeTools(heard={"desmond": heard}), out=out)

    assert clip.status.startswith("not imported")
    assert clip.problems == ["word error rate 28%", "ending missing"]
    assert npcs.imported_voices() == {}
    assert npcs.clip_path("desmond").with_suffix(".txt").read_text() == LINES["desmond"] + "\n"


def test_force_imports_a_clip_that_fails_the_length_and_whisper_checks(
    content: Path, incoming: Path, out: Path
) -> None:
    drop(incoming, "desmond", 30.0)

    [clip] = run(incoming, FakeTools(heard={"desmond": "Something else"}), force=True, out=out)

    assert clip.status == "imported"
    assert clip.problems == ["30.0 s long, not 5-25 s", "word error rate 100%", "ending missing"]
    assert set(npcs.imported_voices()) == {"desmond"}


@pytest.mark.parametrize(
    ("transcript", "error"),
    [
        ("Kia orana, come in.", "the transcript is 4 words"),
        (" ".join([LINES["desmond"]] * 2), "the transcript is 36 words"),
        (LINES["desmond"].replace("together.", "together!"), "has a '!'"),
    ],
)
def test_force_never_imports_a_transcript_that_cant_be_a_reference_line(
    content: Path, incoming: Path, out: Path, transcript: str, error: str
) -> None:
    drop(incoming, "desmond", transcript=transcript)
    tools = FakeTools()

    [clip] = run(incoming, tools, force=True, out=out)

    assert clip.status == "can't import"
    assert error in clip.errors[0]
    assert tools.transcribed == []
    assert npcs.imported_voices() == {}


def test_unknown_ids_are_reported_not_guessed(
    content: Path, incoming: Path, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drop(incoming, "Desmond", transcript=LINES["desmond"])
    write_wav(incoming / "bob.m4a", 8.0)
    before = snapshot(content)

    assert run(incoming, FakeTools(), out=out) == []

    printed = capsys.readouterr().out
    assert "Unknown resident 'Desmond': Desmond.wav, Desmond.txt" in printed
    assert "Unknown resident 'bob': bob.m4a" in printed
    assert "Name each clip and transcript after a resident: desmond, priya" in printed
    assert snapshot(content) == before


def test_a_missing_transcript_is_reported(
    content: Path, incoming: Path, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_wav(incoming / "desmond.wav", 8.0)
    tools = FakeTools()

    assert run(incoming, tools, out=out) == []

    assert "desmond: no transcript. Add desmond.txt with exactly what desmond.wav says" in capsys.readouterr().out
    assert tools.transcribed == []


def test_residents_without_a_clip_are_left_alone(
    content: Path, incoming: Path, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drop(incoming, "desmond")
    (incoming / "priya.txt").write_text(LINES["priya"])
    (incoming / ".DS_Store").write_bytes(b"")
    (incoming / "notes.md").write_text("to do")

    clips = run(incoming, FakeTools(), out=out)

    assert [clip.npc_id for clip in clips] == ["desmond"]
    printed = capsys.readouterr().out
    assert "No clip for priya: left alone" in printed
    assert "Ignored notes.md: clips must be .wav, .mp3 or .m4a" in printed
    assert ".DS_Store" not in printed


def test_two_clips_for_one_resident_are_reported(
    content: Path, incoming: Path, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drop(incoming, "desmond")
    write_wav(incoming / "desmond.mp3", 8.0)

    assert run(incoming, FakeTools(), out=out) == []

    assert "desmond: desmond.mp3 and desmond.wav are both clips for them. Keep one" in capsys.readouterr().out


def test_a_clip_that_wont_convert_is_reported(content: Path, incoming: Path, out: Path) -> None:
    (incoming / "desmond.m4a").write_bytes(b"not audio")
    (incoming / "desmond.txt").write_text(LINES["desmond"])

    [clip] = run(incoming, FakeTools(), force=True, out=out)

    assert clip.status == "can't import"
    assert clip.errors == ["couldn't convert desmond.m4a: Couldn't open input file"]


def test_a_north_american_accent_warns_but_doesnt_block(content: Path, incoming: Path, out: Path) -> None:
    drop(incoming, "desmond")

    [clip] = run(incoming, FakeTools(accents={"desmond": "canada 60%, us 30%", "desmond_2": "us 81%"}), out=out)

    assert clip.status == "imported"
    assert clip.warnings == [
        "the clip sounds North American (canada 60%, us 30%)",
        "sample 2 sounds North American (us 81%)",
    ]
    assert clip.sample_accents == ["australia 99%", "us 81%", "australia 99%"]


def test_an_unchanged_import_is_skipped_unless_forced(
    content: Path, incoming: Path, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drop(incoming, "desmond")
    run(incoming, FakeTools(), out=out)
    again = FakeTools()

    assert run(incoming, again, out=out) == []
    assert "desmond: already imported from desmond.wav. --force imports it again" in capsys.readouterr().out
    assert again.transcribed == []

    [clip] = run(incoming, again, force=True, out=out)
    assert clip.status == "imported"

    drop(incoming, "desmond", transcript=NEW_LINE)
    [clip] = run(incoming, FakeTools(), out=out)
    assert clip.status == "imported"


def test_only_imports_the_residents_named(content: Path, incoming: Path, out: Path) -> None:
    drop(incoming, "desmond")
    drop(incoming, "priya")
    tools = FakeTools()

    clips = run(incoming, tools, only={"priya"}, out=out)

    assert [clip.npc_id for clip in clips] == ["priya"]
    assert tools.spoken == [["priya"]]
    with pytest.raises(SystemExit, match="no such resident: bob"):
        run(incoming, tools, only={"bob"}, out=out)


class Mute(FakeTools):
    def speak(self, npc_ids: list[str]) -> None:
        raise subprocess.CalledProcessError(1, "speak_npcs.py")


def test_a_failed_speak_npcs_says_how_to_rerun_it(content: Path, incoming: Path, out: Path) -> None:
    drop(incoming, "desmond")

    with pytest.raises(SystemExit, match="speak_npcs.py desmond --force"):
        run(incoming, Mute(), out=out)

    assert set(npcs.imported_voices()) == {"desmond"}


class Unmeasured(FakeTools):
    def measure(self, npc_ids: list[str]) -> None:
        raise subprocess.CalledProcessError(1, "simile voice measure")


def test_a_failed_measurement_says_how_to_rerun_it(content: Path, incoming: Path, out: Path) -> None:
    drop(incoming, "desmond")
    drop(incoming, "priya")

    with pytest.raises(SystemExit, match="simile voice measure desmond priya"):
        run(incoming, Unmeasured(), out=out)

    assert set(npcs.imported_voices()) == {"desmond", "priya"}


def test_measures_rates_with_the_servers_command(content: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: runs.append((command, kwargs)))

    npcs.measure_rates(["desmond", "priya"])

    [(command, kwargs)] = runs
    assert command[:3] == ["uv", "run", "--project"] and command[3] == npcs.REPO_ROOT / "server"
    assert command[4:] == ["--extra", "voice", "simile", "voice", "measure", "desmond", "priya"]
    assert kwargs == {"check": True}


def test_design_never_redesigns_an_imported_voice(content: Path) -> None:
    residents = npcs.load_npcs()
    npcs.save_imported({"desmond": "digest"})

    assert npcs.to_design(residents, force=True).keys() == {"priya"}
    assert npcs.to_design(residents, force=False) == {}


def test_design_gives_a_resident_a_voice_once_their_imported_one_is_gone(content: Path) -> None:
    npcs.save_imported({"desmond": "digest"})
    regenerated = resident("desmond", LINES["desmond"])
    regenerated["voice"]["reference_clip"] = None
    (content / "npcs" / "desmond.json").write_text(n1_json(regenerated), encoding="utf-8")

    assert npcs.to_design(npcs.load_npcs(), force=False).keys() == {"desmond"}


def test_removing_a_voice_forgets_its_import(content: Path) -> None:
    npcs.save_imported({"desmond": "digest", "priya": "digest"})

    npcs.remove_voice("desmond")

    assert npcs.imported_voices() == {"priya": "digest"}
    assert not npcs.clip_path("desmond").exists()


def test_scripts_are_the_reference_lines(content: Path, incoming: Path) -> None:
    (incoming / "priya.txt").write_text("my own words")

    write_scripts(incoming, None)

    assert (incoming / "desmond.txt").read_text() == LINES["desmond"] + "\n"
    assert (incoming / "priya.txt").read_text() == "my own words"


@pytest.mark.skipif(shutil.which("afconvert") is None, reason="needs macOS's afconvert")
def test_converts_any_clip_to_24khz_mono_16_bit_pcm(tmp_path: Path) -> None:
    write_wav(tmp_path / "stereo.wav", 6.0, rate=44_100, channels=2)
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", tmp_path / "stereo.wav", tmp_path / "clip.m4a"], check=True)

    for source in ["stereo.wav", "clip.m4a"]:
        wav = tmp_path / f"{source}.converted.wav"
        convert(tmp_path / source, wav)
        with wave.open(str(wav)) as reader:
            assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (1, 2, SAMPLE_RATE)
            assert reader.getnframes() / reader.getframerate() == pytest.approx(6.0, abs=0.1)
        assert wav.read_bytes()[20:22] == (1).to_bytes(2, "little")

    (tmp_path / "junk.m4a").write_bytes(b"not audio")
    with pytest.raises(ConversionError):
        convert(tmp_path / "junk.m4a", tmp_path / "junk.wav")


def test_rewriting_a_committed_npc_keeps_n1s_formatting() -> None:
    for path in sorted(COMMITTED_NPCS.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert n1_json(json.loads(text)) == text, path.name
