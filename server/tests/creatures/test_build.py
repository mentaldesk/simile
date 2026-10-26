import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from simile.creatures import build
from simile.creatures.build import (
    PPM,
    components,
    fingerprint,
    guide,
    problems,
    seed,
    tidied,
)
from simile.creatures.catalogue import CREATURES, Edit
from simile.creatures.preview import SCENE_W, write_preview

BACKGROUND = (214, 214, 216)
BODY = (120, 96, 80)


def body(size: tuple[int, int], colour: tuple[int, int, int] = BODY) -> Image.Image:
    out = Image.new("RGB", size, BACKGROUND)
    w, h = size
    ImageDraw.Draw(out).ellipse((0.25 * w, 0.3 * h, 0.75 * w, 0.8 * h), colour, (40, 26, 20), 4)
    return out


class Fake:
    """Paints a body from words, and over a guide paints the body whole again."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        self.calls.append((prompt, seed, len(images)))
        return body(size)


class Painters:
    def __init__(self, fake: Fake | None = None) -> None:
        self.loaded = 0
        self.fake = fake or Fake()

    @contextmanager
    def __call__(self) -> Iterator[Fake]:
        self.loaded += 1
        yield self.fake


def keyed(painting: Image.Image) -> Image.Image:
    rgb = np.asarray(painting.convert("RGB"), dtype=np.int16)
    away = np.abs(rgb - np.array(BACKGROUND)).max(axis=2) > 12
    return Image.fromarray(np.dstack([rgb.astype(np.uint8), (away * 255).astype(np.uint8)]))


def made(tmp_path: Path, painters: Painters, **kwargs) -> list:
    kwargs = {"cache": tmp_path / "cache", "cut": keyed, "log": lambda _: None} | kwargs
    return build.build(painters, tmp_path / "out", **kwargs)


def test_paints_every_creature_and_a_rerun_paints_nothing(tmp_path: Path) -> None:
    painters = Painters()

    made(tmp_path, painters)
    again = made(tmp_path, Painters())

    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == sorted(f"{c}.{ext}" for c in CREATURES for ext in ("json", "webp"))
    assert painters.loaded == 1
    assert again == []


def test_paints_the_first_frame_from_the_reference_then_each_other_over_a_guide(
    tmp_path: Path,
) -> None:
    painters = Painters()

    made(tmp_path, painters, only=["bat"])

    bat = CREATURES["bat"]
    prompts = [prompt for prompt, _, _ in painters.fake.calls]
    assert prompts == [bat.prompt(frame) for frame in bat.frames]
    assert "style of the reference picture" in prompts[0]
    assert all("Redraw image 1" in p for p in prompts[1:])
    assert [n for _, _, n in painters.fake.calls] == [1] * len(bat.frames)


def test_the_manifest_has_every_frame_and_pose(tmp_path: Path) -> None:
    made(tmp_path, Painters(), only=["dog"])

    found = json.loads((tmp_path / "out" / "dog.json").read_text())
    dog = CREATURES["dog"]
    with Image.open(tmp_path / "out" / "dog.webp") as atlas:
        size = atlas.size
    assert found["hash"] == fingerprint(dog)
    assert found["ppm"] == PPM
    assert found["moves"] == "walk"
    assert set(found["frames"]) == set(dog.frames)
    assert found["poses"] == dog.poses
    for entry in found["frames"].values():
        x, y, w, h = entry["frame"]
        assert x + w <= size[0] and y + h <= size[1]
    first = found["frames"]["stand"]
    assert first["frame"][2] == pytest.approx(dog.length * PPM, abs=6)
    assert first["anchor"][1] == pytest.approx(first["frame"][3], abs=3)
    assert found["size"][0] == pytest.approx(dog.length, abs=0.1)


def test_a_hanging_frame_hangs_from_its_top(tmp_path: Path) -> None:
    made(tmp_path, Painters(), only=["bat"])

    frames = json.loads((tmp_path / "out" / "bat.json").read_text())["frames"]
    assert frames["roost"]["hangs"] is True
    assert frames["roost"]["anchor"][1] == pytest.approx(2, abs=2)
    assert "hangs" not in frames["glide"]


def test_a_changed_entry_repaints_only_that_creature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(tmp_path, Painters(), cache=None)
    changed = replace(CREATURES["rat"], words="a different rat.")
    monkeypatch.setitem(CREATURES, "rat", changed)

    painters = Painters()
    done = made(tmp_path, painters, cache=None)

    assert [p.creature.id for p in done] == ["rat"]
    assert painters.loaded == 1


def test_cached_paintings_are_cut_again_without_the_painter(tmp_path: Path) -> None:
    made(tmp_path, Painters(), only=["rat"])

    painters = Painters()
    made(tmp_path, painters, only=["rat"], force=True)

    assert painters.loaded == 0


def test_a_frame_painted_off_colour_is_painted_again_a_few_times_at_most(
    tmp_path: Path,
) -> None:
    class Blue(Fake):
        def paint(self, prompt, size, seed, images=()):
            painted = super().paint(prompt, size, seed, images)
            return body(size, (40, 60, 200)) if "lunging" in prompt else painted

    painters = Painters(Blue())

    done = made(tmp_path, painters, only=["rat"])

    tries = done[0].tries["attack"]
    assert len(tries) == CREATURES["rat"].tries
    assert all("off colour" in p for t in tries for p in t.problems)
    assert sorted(t.seed for t in tries) == sorted(seed("rat", "attack", n) for n in range(3))


def test_a_reroll_paints_that_frame_with_another_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(CREATURES, "rat", replace(CREATURES["rat"], rerolls={"pass": 2}))
    painters = Painters()

    made(tmp_path, painters, only=["rat"])

    assert seed("rat", "pass", 2) in [s for _, s, _ in painters.fake.calls]


def test_unknown_creatures_are_refused(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="No creature called dragon"):
        made(tmp_path, Painters(), only=["dragon"])


def test_a_guide_paints_out_its_boxes_and_turns() -> None:
    painting = Image.new("RGB", (200, 200), BACKGROUND)
    ImageDraw.Draw(painting).rectangle((50, 90, 150, 110), BODY)
    figure = keyed(painting)

    rubbed = np.asarray(guide(painting, figure, Edit("", "stand", rub=((-0.1, -0.1, 0.5, 1.1),))))
    turned = np.asarray(guide(painting, figure, Edit("", "stand", turn=90)))

    assert (rubbed[100, 60] == BACKGROUND).all()
    assert (rubbed[100, 140] == BODY).all()
    assert (turned[60, 100] == BODY).all()
    assert (turned[100, 60] == BACKGROUND).all()


def test_a_guide_mirrors_its_box_down_over_the_figure() -> None:
    painting = Image.new("RGB", (100, 100), BACKGROUND)
    draw = ImageDraw.Draw(painting)
    draw.rectangle((10, 10, 30, 40), (200, 0, 0))
    draw.rectangle((40, 40, 80, 70), BODY)
    figure = keyed(painting)

    mirrored = np.asarray(guide(painting, figure, Edit("", "up", mirror=(0, 0, 0.3, 0.5))))

    assert (mirrored[20, 20] == BACKGROUND).all()
    assert (mirrored[60, 20] == (200, 0, 0)).all()
    assert (mirrored[60, 60] == BODY).all()
    assert (mirrored[45, 20] == (200, 0, 0)).all()


def test_components_join_at_corners() -> None:
    mask = np.zeros((6, 8), dtype=bool)
    mask[0, 0:2] = mask[1, 1] = mask[1, 2] = True
    mask[3:5, 4:7] = mask[5, 7] = True

    labels, sizes = components(mask)

    assert sorted(sizes) == [4, 7]
    assert labels[0, 0] == labels[1, 2] != labels[5, 7]


def test_specks_apart_from_the_body_are_cut_away() -> None:
    painting = body((200, 100))
    ImageDraw.Draw(painting).rectangle((5, 5, 7, 7), (0, 0, 0))

    tidy = np.asarray(tidied(keyed(painting)))

    assert tidy[6, 6, 3] == 0
    assert tidy[50, 100, 3] == 255


def test_what_is_wrong_with_a_frame() -> None:
    first = keyed(body((200, 100)))
    edge = Image.new("RGB", (200, 100), BACKGROUND)
    ImageDraw.Draw(edge).rectangle((0, 20, 120, 80), BODY)
    halves = Image.new("RGB", (200, 100), BACKGROUND)
    ImageDraw.Draw(halves).rectangle((20, 20, 60, 80), BODY)
    ImageDraw.Draw(halves).rectangle((120, 20, 160, 80), BODY)

    assert problems(first, first) == ([], 0.0)
    assert "cut off by the edge" in problems(keyed(edge), first)[0]
    assert "in pieces" in problems(keyed(halves), first)[0]
    tiny = Image.new("RGB", (200, 100), BACKGROUND)
    ImageDraw.Draw(tiny).rectangle((90, 40, 100, 50), BODY)
    assert any("times the first frame's size" in p for p in problems(keyed(tiny), first)[0])


def test_the_preview_is_drawn_from_what_was_written(tmp_path: Path) -> None:
    made(tmp_path, Painters())

    path = write_preview(tmp_path / "out")

    with Image.open(path) as sheet:
        assert sheet.width >= SCENE_W
    with Image.open(tmp_path / "out" / "cycles.webp") as played:
        assert played.n_frames == 4
