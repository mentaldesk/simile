import ast
import importlib.util
import json
import re
import shutil
import subprocess
import zlib
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.clinic.doctor import load_doctor
from simile.npc import NPCS_DIR, load_npcs
from simile.schema import Character, CoreValue
from simile.voicing import gpu, greetings, speak
from simile.voicing.greetings import (
    GREETINGS,
    LINES,
    REPO_ROOT,
    TONES,
    Greeting,
    digest,
    files,
    lines_for,
    load_lines,
    load_made,
    outdated,
    remove,
)

BUDGET = 1024 * 1024
POOL = REPO_ROOT / "content" / "characters" / "pool"
residents = [*load_npcs(NPCS_DIR), load_doctor()]
voiced = [npc for npc in residents if npc.voice.reference_clip]


def test_every_voiced_resident_has_three_or_four_greetings() -> None:
    lines = load_lines()

    assert voiced
    for npc in voiced:
        assert 3 <= len(lines[npc.id]) <= 4, npc.id
        assert [path.name for path in files(GREETINGS, npc.id)] == [
            f"{npc.id}_{n}.m4a" for n in range(1, len(lines[npc.id]) + 1)
        ]


def test_greetings_are_up_to_date_with_each_voice_and_line() -> None:
    stale = [npc.id for npc in outdated(voiced, load_lines(), load_made())]

    assert stale == [], "run `uv run --extra voice simile greetings` on a Mac with Apple Silicon"


def test_greetings_are_short_and_small() -> None:
    made = load_made()
    recorded = sorted(GREETINGS.glob("*.m4a"))

    assert sum(path.stat().st_size for path in recorded) <= BUDGET
    for path in recorded:
        assert path.read_bytes()[4:12] == b"ftypM4A ", path.name
    for npc in voiced:
        assert all(0.5 <= seconds <= 2.5 for seconds in made[npc.id].seconds), npc.id
    assert {path.stem.rsplit("_", 1)[0] for path in recorded} == {npc.id for npc in voiced}


def test_greetings_fit_any_player() -> None:
    names = {word.lower() for npc in residents for word in npc.name.split()}

    for id, lines in load_lines().items():
        for line in lines:
            words = set(re.findall(r"[a-z']+", line.text.lower()))
            assert not words & (names | {"sir", "madam", "player", "visitor"}), (id, line.text)
            assert not words & {"morning", "evening", "night", "afternoon"}, (id, line.text)


def test_digest_follows_the_lines_and_the_clip() -> None:
    npc = voiced[0]
    lines = [Greeting(text="Hello there.")]

    assert digest(npc.voice, lines) == digest(npc.voice, [Greeting(text="Hello there.", take=0)])
    assert digest(npc.voice, lines) != digest(npc.voice, [Greeting(text="Hello there.", take=1)])
    other = npc.voice.model_copy(update={"reference_clip": voiced[1].voice.reference_clip})
    assert digest(npc.voice, lines) != digest(other, lines)


def test_files_come_in_order(tmp_path: Path) -> None:
    for name in ("ada_10.m4a", "ada_2.m4a", "ada_1.m4a", "ada_x.m4a", "adam_1.m4a", "ada_3.wav"):
        (tmp_path / name).touch()

    assert [path.name for path in files(tmp_path, "ada")] == ["ada_1.m4a", "ada_2.m4a"]
    remove(tmp_path, "ada")
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "ada_10.m4a",
        "ada_3.wav",
        "ada_x.m4a",
        "adam_1.m4a",
    ]


def character(id: str = "abena_asamoah", **values: float) -> Character:
    data = json.loads((POOL / f"{id}.json").read_text())
    data["values"] = {value.value: 0.3 for value in CoreValue} | values
    data["speaking_style"] = "Even and plain, with short sentences."
    return Character.model_validate(data)


def test_a_new_character_gets_four_greetings_in_their_way_of_talking() -> None:
    formal = lines_for(character(obedience=0.9, tradition=0.9, discipline=0.8))
    playful = lines_for(character(adventure=0.9, pleasure=0.9, optimism=0.8))

    assert len(formal) == len(playful) == len(set(formal)) == 4
    assert sum(line in TONES["formal"] for line in formal) == 3
    assert sum(line in TONES["playful"] for line in playful) == 3
    assert formal == lines_for(character(obedience=0.9, tradition=0.9, discipline=0.8))
    assert all(len(line) <= 40 for tone in TONES.values() for line in tone)


def test_a_new_character_says_the_hello_their_style_quotes() -> None:
    quoted = character().model_copy(
        update={"speaking_style": "Slow and warm. She opens with 'Kia ora' and laughs."}
    )

    assert lines_for(quoted)[0] == "Kia ora!"
    assert len(lines_for(quoted)) == 4


def test_seeds_each_greeting_as_v1_seeds_a_sentence() -> None:
    assert speak.seed(2, "kofi", "Hey, my friend!") == zlib.crc32(b"2/kofi/Hey, my friend!")


def test_uses_v1s_voice_model() -> None:
    source = (REPO_ROOT / "server" / "simile" / "voice" / "qwen.py").read_text()
    assigned = {
        node.targets[0].id: node.value.value
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
    }

    assert assigned["MODEL"] == speak.MODEL


def test_trims_the_silence_around_a_greeting() -> None:
    rate = speak.SAMPLE_RATE
    voice = 0.3 * np.sin(np.linspace(0, 2 * np.pi * 220, rate)).astype(np.float32)
    audio = np.concatenate(
        [np.zeros(rate // 2), [0.5], np.zeros(rate // 2), voice, np.zeros(rate)]
    ).astype(np.float32)

    trimmed = speak.trimmed(audio)

    expected = rate + round((speak.LEAD_IN + speak.TAIL) * rate)
    assert abs(len(trimmed) - expected) <= speak.WINDOW * speak.SUSTAINED
    assert trimmed[0] == 0 and trimmed[-1] == 0
    assert np.abs(trimmed).max() == pytest.approx(0.3, abs=0.01)


def test_leaves_silence_alone() -> None:
    quiet = np.zeros(speak.SAMPLE_RATE, dtype=np.float32)

    assert len(speak.trimmed(quiet)) == len(quiet)


@pytest.mark.skipif(shutil.which("afconvert") is None, reason="needs macOS's afconvert")
def test_encodes_a_small_m4a(tmp_path: Path) -> None:
    rate = speak.SAMPLE_RATE
    audio = (0.3 * np.sin(np.linspace(0, 2 * np.pi * 300, rate))).astype(np.float32)

    speak.encode(audio, tmp_path / "hello.m4a")

    info = subprocess.run(
        ["afinfo", str(tmp_path / "hello.m4a")], capture_output=True, text=True, check=True
    ).stdout
    assert "aac" in info and "24000 Hz" in info
    assert (tmp_path / "hello.m4a").stat().st_size < 12_000


def test_the_job_says_what_its_work_directory_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = {
        "voice": "wren",
        "clip": "/clips/wren.wav",
        "transcript": "A line.",
        "lines": ["Hi!", "Hello there."],
    }
    (tmp_path / "greetings.json").write_text(json.dumps(asked))
    calls = []
    monkeypatch.setattr(speak, "load", lambda: "model")

    def said(model, voice, clip, transcript, lines, out, progress):
        calls.append((model, voice, clip, transcript, lines, out))
        progress(0.5, "halfway")
        return [0.8, 1.1]

    monkeypatch.setattr(speak, "speak", said)

    speak.main([str(tmp_path)])

    assert calls == [
        (
            "model",
            "wren",
            Path("/clips/wren.wav"),
            "A line.",
            [("Hi!", 0), ("Hello there.", 0)],
            tmp_path,
        )
    ]
    assert json.loads((tmp_path / "spoken.json").read_text()) == {"seconds": [0.8, 1.1]}
    assert 'JOB {"progress": 0.5, "message": "halfway"}' in capsys.readouterr().out


def test_the_command_says_when_every_greeting_is_up_to_date() -> None:
    before = (GREETINGS / "made.json").read_bytes()

    result = CliRunner().invoke(create_cli(), ["greetings"])

    assert result.exit_code == 0, result.output
    assert "Every greeting is up to date" in result.output
    assert (GREETINGS / "made.json").read_bytes() == before


def test_the_command_refuses_an_unknown_resident() -> None:
    result = CliRunner().invoke(create_cli(), ["greetings", "nobody"])

    assert result.exit_code != 0
    assert "no such resident: nobody" in result.output


def test_the_command_says_the_out_of_date_greetings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "lines.json").write_text(json.dumps({"tobias": [{"text": "Hello there."}]}))
    (tmp_path / "tobias_2.m4a").write_bytes(b"old")
    monkeypatch.setattr(greetings, "GREETINGS", tmp_path)
    monkeypatch.setattr(greetings, "LINES", tmp_path / "lines.json")
    monkeypatch.setattr(greetings, "MADE", tmp_path / "made.json")
    monkeypatch.setattr(gpu, "wait_for_gpu", lambda say: None)
    find_spec, which = importlib.util.find_spec, shutil.which
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: object() if name == "mlx_audio" else find_spec(name, *a),
    )
    monkeypatch.setattr(
        shutil, "which", lambda name: "afconvert" if name == "afconvert" else which(name)
    )
    monkeypatch.setattr(speak, "load", lambda: "model")
    asked = []

    def said(model, voice, clip, transcript, lines, out):
        asked.append((voice, clip.name, lines, out))
        (out / f"{voice}_1.m4a").write_bytes(b"new")
        return [0.87]

    monkeypatch.setattr(speak, "speak", said)

    result = CliRunner().invoke(create_cli(), ["greetings"])

    assert result.exit_code == 0, result.output
    assert asked == [("tobias", "tobias.wav", [("Hello there.", 0)], tmp_path)]
    assert "tobias: 'Hello there.' 0.87 s" in result.output
    assert [path.name for path in files(tmp_path, "tobias")] == ["tobias_1.m4a"]
    assert load_made(tmp_path / "made.json")["tobias"].seconds == [0.87]
    again = CliRunner().invoke(create_cli(), ["greetings"])
    assert "Every greeting is up to date" in again.output


def test_waits_for_the_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    others = [["mflux-generate"], ["ollama: qwen3"], []]
    said = []
    monkeypatch.setattr(gpu, "busy", lambda: others.pop(0))
    monkeypatch.setattr(gpu.time, "sleep", lambda seconds: said.append(seconds))

    gpu.wait_for_gpu(said.append, poll=5)

    assert said == ["Waiting for mflux-generate", 5, "Waiting for ollama: qwen3", 5]


def test_lines_file_holds_only_residents() -> None:
    assert load_lines().keys() <= {npc.id for npc in residents}
    assert LINES.is_file()


@pytest.mark.mlx
def test_says_a_greeting_in_a_residents_voice(tmp_path: Path) -> None:
    npc = next(npc for npc in voiced if npc.id == "tobias")
    assert npc.voice.reference_clip is not None
    if others := gpu.busy():
        pytest.skip(f"another model holds the GPU: {'; '.join(others)}")
    model = speak.load()

    seconds = speak.speak(
        model,
        npc.id,
        REPO_ROOT / npc.voice.reference_clip,
        npc.voice.reference_line,
        [("Hello there.", 0)],
        tmp_path,
    )

    assert 0.4 <= seconds[0] <= 2.0
    assert (tmp_path / "tobias_1.m4a").stat().st_size < 20_000
