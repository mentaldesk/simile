import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image

from simile.dolls import build
from simile.dolls.paint import FakeSheetPainter
from simile.dolls.shapes import PIECES
from simile.dolls.sheet import LAYOUTS


class Painters:
    """Counts how often the painter is loaded and how many sheets it paints."""

    def __init__(self) -> None:
        self.loaded = 0
        self.fake = FakeSheetPainter()

    @contextmanager
    def __call__(self) -> Iterator[FakeSheetPainter]:
        self.loaded += 1
        yield self.fake


def stamps(directory: Path) -> dict[str, int]:
    return {path.name: path.stat().st_mtime_ns for path in directory.iterdir()}


@pytest.fixture
def two(monkeypatch: pytest.MonkeyPatch) -> dict:
    everyone = build.people()
    chosen = {who: everyone[who] for who in ("odalys", "player")}
    monkeypatch.setattr(build, "people", lambda: dict(chosen))
    return chosen


def test_paints_each_doll_and_a_rerun_rewrites_nothing(tmp_path: Path, two: dict) -> None:
    painters = Painters()

    build.build(painters, tmp_path, cache=None, log=lambda _: None)
    before = stamps(tmp_path)
    build.build(painters, tmp_path, cache=None, log=lambda _: None)

    assert sorted(before) == [
        "odalys-flat.webp",
        "odalys-painted.webp",
        "odalys.json",
        "player-flat.webp",
        "player-painted.webp",
        "player.json",
    ]
    assert painters.loaded == 1
    assert len(painters.fake.calls) == 2 * len(LAYOUTS)
    assert stamps(tmp_path) == before


def test_a_changed_appearance_repaints_only_that_doll(tmp_path: Path, two: dict) -> None:
    painters = Painters()
    build.build(painters, tmp_path, cache=None, log=lambda _: None)
    player = stamps(tmp_path)["player.json"]

    two["odalys"] = two["odalys"].model_copy(update={"top_colour": "#124e89"})
    done = build.build(painters, tmp_path, cache=None, log=lambda _: None)

    assert [painted.who for painted in done] == ["odalys"]
    assert stamps(tmp_path)["player.json"] == player
    manifest = json.loads((tmp_path / "odalys.json").read_text())
    assert manifest["appearance"]["top_colour"] == "#124e89"
    assert manifest["hash"] == build.fingerprint("odalys", two["odalys"])


def test_cached_paintings_are_cut_again_without_the_painter(tmp_path: Path, two: dict) -> None:
    painters = Painters()
    build.build(painters, tmp_path / "a", only=["player"], cache=tmp_path / "cache")

    build.build(painters, tmp_path / "b", only=["player"], cache=tmp_path / "cache")

    assert painters.loaded == 1
    for name in ("player.json", "player-flat.webp", "player-painted.webp"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_a_reroll_paints_that_sheet_with_another_seed(
    tmp_path: Path, two: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    painters = Painters()
    build.build(painters, tmp_path, only=["player"], cache=None, log=lambda _: None)
    first = [seed for _, seed in painters.fake.calls]

    monkeypatch.setitem(build.REROLLS, "player/front_back", 1)
    build.build(painters, tmp_path, only=["player"], cache=None, log=lambda _: None)

    side, front_back = (seed for _, seed in painters.fake.calls[len(first) :])
    assert side == first[0] and front_back != first[1]


def test_the_manifest_frames_every_piece_inside_both_atlases(tmp_path: Path, two: dict) -> None:
    build.build(Painters(), tmp_path, only=["odalys"], cache=None, log=lambda _: None)

    manifest = json.loads((tmp_path / "odalys.json").read_text())
    flat = Image.open(tmp_path / manifest["flat"])
    painted = Image.open(tmp_path / manifest["painted"])

    assert manifest["id"] == "odalys" and manifest["unit"] == 5.0
    assert set(manifest["pieces"]) == set(PIECES)
    assert flat.size == painted.size
    for name, piece in manifest["pieces"].items():
        x, y, w, h = piece["frame"]
        assert x + w <= flat.width and y + h <= flat.height, name
        box = (x, y, x + w, y + h)
        assert flat.crop(box).getchannel("A").getbbox() is not None, name
        assert painted.crop(box).getchannel("A").getbbox() is not None, name


def test_unknown_people_are_refused(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="nobody"):
        build.build(Painters(), tmp_path, only=["nobody"], cache=None)
