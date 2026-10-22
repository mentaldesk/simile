import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from simile.dolls import build
from simile.dolls.figure import FRAMES, POSES
from simile.dolls.flux import FakePainter, figure
from simile.dolls.measure import MARKS

from .keyed import keyed


class Painters:
    """Counts how often the painter is loaded and what it paints."""

    def __init__(self, fake: FakePainter | None = None) -> None:
        self.loaded = 0
        self.fake = fake or FakePainter()

    @contextmanager
    def __call__(self) -> Iterator[FakePainter]:
        self.loaded += 1
        yield self.fake


class Mistakes(FakePainter):
    """Paints the standing figure's top blue, whatever it's asked for."""

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        if images:
            return super().paint(prompt, size, seed, images)
        self.calls.append((prompt, seed, 0))
        colours = {"skin": "#e4a672", "hair": "#3e2731", "bottom": "#3a4466", "shoe": "#ffffff"}
        return figure(size, colours | {"top": "#124e89"})


class Bigger(FakePainter):
    """Draws sitting half as big again as standing."""

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        painted = super().paint(prompt, size, seed, images)
        if "sitting" not in prompt:
            return painted
        w, h = size
        crop = painted.crop((w // 6, 0, w - w // 6, round(h / 1.5)))
        return crop.resize(size)


class FacePaint(FakePainter):
    """Paints a blue-grey patch on the cheek of every pose."""

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        painted = super().paint(prompt, size, seed, images)
        w, h = size
        ImageDraw.Draw(painted).ellipse((0.56 * w, 0.17 * h, 0.66 * w, 0.25 * h), (139, 155, 180))
        return painted


def made(painters: Painters, directory: Path, **kwargs) -> list[build.Painted]:
    return build.build(painters, directory, cut=keyed, log=lambda _: None, **kwargs)


def stamps(directory: Path) -> dict[str, int]:
    return {path.name: path.stat().st_mtime_ns for path in directory.iterdir()}


@pytest.fixture
def two(monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(build, "SIZE", (192, 256))
    everyone = build.people()
    chosen = {who: everyone[who] for who in ("odalys", "player")}
    monkeypatch.setattr(build, "people", lambda: dict(chosen))
    return chosen


def test_paints_each_figure_and_a_rerun_rewrites_nothing(tmp_path: Path, two: dict) -> None:
    painters = Painters()

    made(painters, tmp_path, cache=None)
    before = stamps(tmp_path)
    made(painters, tmp_path, cache=None)

    assert sorted(before) == ["odalys.json", "odalys.webp", "player.json", "player.webp"]
    assert painters.loaded == 1
    assert len(painters.fake.calls) == 2 * len(FRAMES)
    assert stamps(tmp_path) == before


def test_paints_standing_from_text_then_every_pose_as_an_edit(tmp_path: Path, two: dict) -> None:
    painters = Painters()

    made(painters, tmp_path, only=["odalys"], cache=None)

    prompts = painters.fake.calls
    assert prompts[0][2] == 0 and "A woman of 27." in prompts[0][0]
    assert all(images == 1 for _, _, images in prompts[1:])
    manifest = json.loads((tmp_path / "odalys.json").read_text())
    assert set(manifest["frames"]) == set(FRAMES)
    assert manifest["poses"] == POSES
    assert manifest["painted"] == "odalys.webp"


def test_a_changed_appearance_repaints_only_that_figure(tmp_path: Path, two: dict) -> None:
    painters = Painters()
    made(painters, tmp_path, cache=None)
    player = stamps(tmp_path)["player.json"]

    two["odalys"] = two["odalys"].model_copy(update={"top_colour": "#124e89"})
    done = made(painters, tmp_path, cache=None)

    assert [painted.who for painted in done] == ["odalys"]
    assert stamps(tmp_path)["player.json"] == player
    manifest = json.loads((tmp_path / "odalys.json").read_text())
    assert manifest["appearance"]["top_colour"] == "#124e89"
    assert manifest["hash"] == build.fingerprint("odalys", two["odalys"], "A woman of 27.")


def test_cached_paintings_are_cut_again_without_the_painter(tmp_path: Path, two: dict) -> None:
    painters = Painters()
    made(painters, tmp_path / "a", only=["player"], cache=tmp_path / "cache")

    made(painters, tmp_path / "b", only=["player"], cache=tmp_path / "cache")

    assert painters.loaded == 1
    for name in ("player.json", "player.webp"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_a_reroll_paints_that_frame_with_another_seed(
    tmp_path: Path, two: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    painters = Painters()
    made(painters, tmp_path, only=["player"], cache=None)
    first = [seed for _, seed, _ in painters.fake.calls]

    monkeypatch.setitem(build.REROLLS, "player/sit", 1)
    made(painters, tmp_path, only=["player"], cache=None)

    again = [seed for _, seed, _ in painters.fake.calls[len(first) :]]
    sit = list(build.EDITS).index("sit") + 1
    assert again[:sit] == first[:sit] and again[sit] != first[sit]


def test_a_painting_in_the_wrong_colours_is_painted_again_a_few_times_at_most(
    tmp_path: Path, two: dict
) -> None:
    painters = Painters(Mistakes())

    done = made(painters, tmp_path, only=["odalys"], cache=None)

    stands = [call for call in painters.fake.calls if call[2] == 0]
    assert len(stands) == build.TRIES["stand"]
    assert len({seed for _, seed, _ in stands}) == len(stands)
    kept = done[0].tries["stand"][-1]
    assert kept.raw["top"].delta_e > build.WRONG
    assert len(done[0].tries["stand"]) == build.TRIES["stand"]
    assert all(len(done[0].tries[frame]) == 1 for frame in ("stride", "run", "sit", "climb"))


def test_a_pose_drawn_at_another_size_is_painted_again_then_scaled_to_the_rest(
    tmp_path: Path, two: dict
) -> None:
    done = made(Painters(Bigger()), tmp_path, only=["player"], cache=None)

    sits = done[0].tries["sit"]
    assert len(sits) == build.TRIES["edit"]
    assert sits[-1].scale == pytest.approx(1.5, abs=0.1)
    manifest = json.loads((tmp_path / "player.json").read_text())
    heights = {name: frame["frame"][3] for name, frame in manifest["frames"].items()}
    assert heights["sit"] < heights["stand"] * 1.05


def test_a_face_painted_over_is_painted_again(tmp_path: Path, two: dict) -> None:
    done = made(Painters(FacePaint()), tmp_path, only=["player"], cache=None)

    assert len(done[0].tries["stand"]) == build.TRIES["stand"]
    assert done[0].tries["stand"][-1].marks > MARKS
    assert done[0].tries["climb"][-1].marks == 0


def test_colours_painted_a_little_off_are_pulled_back(tmp_path: Path, two: dict) -> None:
    done = made(Painters(), tmp_path, only=["player"], cache=None)

    for frame, tries in done[0].tries.items():
        assert all(s.delta_e < 1 for s in tries[-1].matched.values()), frame


def test_files_nobody_owns_are_removed(tmp_path: Path, two: dict) -> None:
    (tmp_path / "odalys-flat.webp").write_bytes(b"old")
    (tmp_path / "gone.json").write_text("{}")
    (tmp_path / "README.md").write_text("kept")

    made(Painters(), tmp_path, cache=None)

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "README.md",
        "odalys.json",
        "odalys.webp",
        "player.json",
        "player.webp",
    ]


def test_unknown_people_are_refused(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="nobody"):
        made(Painters(), tmp_path, only=["nobody"], cache=None)


def test_seats_are_measured_again_from_the_atlas_without_painting(
    tmp_path: Path, two: dict
) -> None:
    made(Painters(), tmp_path, cache=None)
    built = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    for who in two:
        path = tmp_path / f"{who}.json"
        body = json.loads(path.read_text())
        body["frames"]["sit"]["seat"] = [0.0, 0.0]
        path.write_text(json.dumps(body, indent=2) + "\n")

    rewritten = build.reseat(tmp_path)

    assert sorted(p.name for p in rewritten) == ["odalys.json", "player.json"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == built
    assert build.reseat(tmp_path) == []
