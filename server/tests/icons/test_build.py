import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from simile.icons import build
from simile.icons.build import MANIFEST, SIDE, fingerprint, finished, problems
from simile.icons.catalogue import ICONS, Icon

BACKGROUND = (214, 214, 216)


def blobs(size: tuple[int, int], count: int = 1) -> Image.Image:
    out = Image.new("RGB", size, BACKGROUND)
    w, h = size
    draw = ImageDraw.Draw(out)
    for i in range(count):
        left = 0.2 * w + i * 0.35 * w
        draw.ellipse((left, 0.3 * h, left + 0.25 * w, 0.8 * h), (150, 90, 80), (40, 26, 20), 4)
    return out


class Fake:
    """Paints each icon in as many pieces as it's meant to be in."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        self.calls.append((prompt, seed, len(images)))
        return blobs(size, next((i.pieces for i in ICONS.values() if i.words in prompt), 1))


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


def listed(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "out" / MANIFEST).read_text())


def test_paints_every_icon_and_a_rerun_paints_nothing(tmp_path: Path) -> None:
    painters = Painters()

    made(tmp_path, painters)
    again = made(tmp_path, Painters())

    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == sorted([MANIFEST, *(f"{name}.webp" for name in ICONS)])
    assert list(listed(tmp_path)["icons"]) == list(ICONS)
    assert painters.loaded == 1
    assert again == []


def test_paints_in_the_style_of_the_reference_and_fine_first_time(tmp_path: Path) -> None:
    painters = Painters()

    done = made(tmp_path, painters, only=["kidney", "feet"])

    assert [p.icon.id for p in done] == ["kidney", "feet"]
    assert all(len(p.tries) == 1 and not p.tries[0].problems for p in done)
    assert all(images == 1 for _, _, images in painters.fake.calls)
    assert "reference picture" in painters.fake.calls[0][0]


def test_repaints_only_the_icon_whose_entry_changed_and_keeps_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(tmp_path, Painters(), only=["eye", "kidney"])
    before = listed(tmp_path)["icons"]
    changed = dict(ICONS, eye=Icon("eye", "a glass eye."))
    monkeypatch.setattr(build, "ICONS", changed)

    done = made(tmp_path, Painters(), only=["eye", "kidney"])

    after = listed(tmp_path)["icons"]
    assert [p.icon.id for p in done] == ["eye"]
    assert after["eye"]["hash"] == fingerprint(changed["eye"]) != before["eye"]["hash"]
    assert after["kidney"] == before["kidney"]


def test_drops_an_icon_thats_left_the_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made(tmp_path, Painters(), only=["eye", "kidney"])
    monkeypatch.setattr(build, "ICONS", {"kidney": ICONS["kidney"]})

    made(tmp_path, Painters())

    assert list(listed(tmp_path)["icons"]) == ["kidney"]
    assert not (tmp_path / "out" / "eye.webp").exists()


def test_paints_again_with_another_seed_until_its_whole(tmp_path: Path) -> None:
    class Cropped(Fake):
        def paint(self, prompt, size, seed, images=()):
            painting = super().paint(prompt, size, seed, images)
            if len(self.calls) == 1:
                ImageDraw.Draw(painting).rectangle((0, 0, 40, size[1]), (150, 90, 80))
            return painting

    painted = made(tmp_path, Painters(Cropped()), only=["eye"])[0]

    assert "cut off by the edge" in painted.tries[0].problems
    assert painted.tries[1].problems == []
    assert painted.tries[0].seed != painted.tries[1].seed


def test_refuses_an_icon_that_isnt_there(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="No icon called crown"):
        made(tmp_path, Painters(), only=["crown"])


def test_a_pair_must_be_in_two_pieces_of_about_a_size() -> None:
    one, two = keyed(blobs((400, 300))), keyed(blobs((400, 300), 2))

    assert problems(one) == []
    assert problems(two) == ["in pieces"]
    assert problems(two, pieces=2) == []
    assert problems(one, pieces=2) == ["not in 2 pieces"]


def test_finished_icons_are_cropped_and_at_most_side_long() -> None:
    icon = finished(keyed(blobs((1024, 768))))
    small = finished(keyed(blobs((200, 100))))

    assert max(icon.size) == SIDE + 4
    assert np.asarray(icon.getchannel("A"))[:2].max() == 0
    assert max(small.size) < SIDE


def test_finished_keeps_only_the_share_of_an_icon_its_keep_box_says() -> None:
    whole = finished(keyed(blobs((400, 400))))
    top = finished(keyed(blobs((400, 400))), keep=(0.0, 0.0, 1.0, 0.5))

    assert top.width == whole.width
    assert top.height == pytest.approx(whole.height / 2, abs=4)
