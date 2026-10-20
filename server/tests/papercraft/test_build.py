import json
import zlib
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import TracebackType

import numpy as np
import pytest
from PIL import Image

from simile.papercraft import build as build_module
from simile.papercraft.build import PPM, Build, tileable
from simile.papercraft.catalogue import LAYERS, fronts, items, paper
from simile.papercraft.layout import Facade, Layout, Mural
from simile.papercraft.village import PAPERS, TILE


class FakePainter:
    """A painting from the prompt alone: a coloured block on white, or the first image redrawn."""

    calls: list[str] = []

    def __enter__(self) -> "FakePainter":
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        pass

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image]
    ) -> Image.Image:
        FakePainter.calls.append(prompt)
        hue = zlib.crc32(prompt.encode()) % 200
        colour = (250, 210, 120) if "at night" in prompt else (hue, 120, 255 - hue)
        picture = Image.new("RGB", size, (255, 255, 255))
        w, h = size
        picture.paste(colour, (w // 5, h // 5, w * 4 // 5, h * 19 // 20))
        return picture


def fake_mask(image: Image.Image) -> Image.Image:
    a = np.asarray(image.convert("RGB"), dtype=np.int16)
    return Image.fromarray(((np.abs(a - 255).max(axis=2) > 20) * 255).astype(np.uint8))


CAFE = Facade("coffee_shop", "high_street", 2, 9, 11, 3, True, 6, (Mural(1, 3, 1.05, 1.9),))
LAYOUT = Layout(
    streets={"high_street": 30},
    facades={"coffee_shop": CAFE},
    rooms={"coffee_shop": ("cafe", "cafe_upstairs", "flat")},
    furniture={"counter": (3, 1), "sofa": (2, 1)},
)
ITEMS = {p.key: p for p in items(LAYOUT)}
PIECES = [
    LAYERS[0],
    next(p for p in LAYERS if p.kind == "ground"),
    next(p for p in LAYERS if p.kind == "layer"),
    next(p for p in LAYERS if p.kind == "strip"),
    paper("living-ochre", PAPERS["living-ochre"]),
    ITEMS["furniture/sofa"],
    ITEMS["furniture/sofa-coral"],
    *fronts(LAYOUT),
]


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Build:
    monkeypatch.setattr(build_module, "WEBP_METHOD", 0)
    FakePainter.calls = []
    return Build(
        PIECES,
        content=tmp_path / "papercraft",
        cache_dir=tmp_path / "cache",
        painter=FakePainter,
        mask=fake_mask,
        key=fake_mask,
        layout=LAYOUT,
    )


def snapshot(folder: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(p.relative_to(folder)): (p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_a_build_writes_every_piece_and_its_manifest_entry(build: Build) -> None:
    report = build.run(log=lambda _: None)

    manifest = json.loads((build.content / "manifest.json").read_text())
    assert {name.split("#")[0] for name in report.painted} == {p.key for p in PIECES}
    assert set(manifest["pieces"]) == {p.key for p in PIECES}
    for key, entry in manifest["pieces"].items():
        image = Image.open(build.content / entry["file"])
        assert entry["file"] == f"{key}.webp"
        assert list(image.size) == entry["size"]
        assert entry["height"] > 0
        assert len(entry["hash"]) == 20


def test_sprites_and_fronts_are_scaled_to_their_height(build: Build) -> None:
    build.run(log=lambda _: None)
    pieces = json.loads((build.content / "manifest.json").read_text())["pieces"]

    sofa = pieces["furniture/sofa"]
    assert sofa["size"][1] == round(0.85 * PPM)
    assert sofa["anchor"] == [0.5, 1.0]
    front = pieces["fronts/coffee_shop"]
    assert front["size"][1] / front["height"] == pytest.approx(PPM, abs=0.5)
    assert front["anchor"][0] == pytest.approx(0.5, abs=0.02)
    assert 0.9 < front["anchor"][1] < 1.0
    assert front["width"] == pytest.approx(CAFE.width * TILE)
    assert front["eaves"] == pytest.approx(CAFE.height * TILE)
    assert pieces["glow/coffee_shop"]["size"] == front["size"]


def test_a_second_run_with_nothing_changed_rewrites_nothing(build: Build) -> None:
    build.run(log=lambda _: None)
    before = snapshot(build.content)
    FakePainter.calls = []

    report = build.run(log=lambda _: None)

    assert report.painted == {} and report.written == []
    assert FakePainter.calls == []
    assert snapshot(build.content) == before


def test_a_changed_prompt_repaints_only_its_piece_and_what_redraws_it(build: Build) -> None:
    build.run(log=lambda _: None)
    sofa = next(p for p in PIECES if p.key == "furniture/sofa")
    changed = [replace(p, prompt=p.prompt + " Blue.") if p is sofa else p for p in PIECES]
    rebuild = Build(
        changed,
        content=build.content,
        cache_dir=build.cache,
        painter=FakePainter,
        mask=fake_mask,
        key=fake_mask,
        layout=LAYOUT,
    )

    report = rebuild.run(log=lambda _: None)

    assert set(report.painted) == {"furniture/sofa", "furniture/sofa-coral"}
    assert set(report.written) == {"furniture/sofa", "furniture/sofa-coral"}


def test_a_new_cut_reuses_the_cached_paintings(
    build: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    build.run(log=lambda _: None)
    monkeypatch.setattr(build_module, "PIPELINE", build_module.PIPELINE + 1)

    report = build.run(log=lambda _: None)

    assert report.painted == {}
    assert set(report.written) == {p.key for p in PIECES}


def test_a_piece_dropped_from_the_catalogue_is_removed(build: Build) -> None:
    build.run(log=lambda _: None)
    rebuild = Build(
        PIECES[1:],
        content=build.content,
        cache_dir=build.cache,
        painter=FakePainter,
        mask=fake_mask,
        key=fake_mask,
        layout=LAYOUT,
    )

    report = rebuild.run(log=lambda _: None)

    assert report.removed == [PIECES[0].key]
    assert not (build.content / f"{PIECES[0].key}.webp").exists()


def test_a_partial_run_paints_only_what_it_was_asked_for(build: Build) -> None:
    report = build.run(lambda key: key.startswith("glow/"), log=lambda _: None)

    painted = {name.split("#")[0] for name in report.painted}
    assert painted == {"fronts/coffee_shop", "glow/coffee_shop"}
    assert report.written == ["glow/coffee_shop"]


def test_the_glow_map_is_dark_away_from_the_windows_and_lamps(build: Build) -> None:
    build.run(log=lambda _: None)
    glow = np.asarray(Image.open(build.content / "glow/coffee_shop.webp").convert("L"))

    assert glow.max() > 100
    assert (glow < 12).mean() > 0.7


def test_a_tileable_paper_meets_itself_at_its_edges() -> None:
    rng = np.random.default_rng(0)
    noise = Image.fromarray(rng.integers(0, 255, (64, 300, 3), dtype=np.uint8))

    tiled = np.asarray(tileable(noise, both=True), dtype=np.int16)

    assert abs(tiled[:, -1] - tiled[:, 0]).mean() < abs(tiled[:, 150] - tiled[:, 0]).mean()


def test_a_layer_with_a_gap_near_each_end_is_cut_at_the_gaps() -> None:
    a = np.zeros((40, 200, 4), dtype=np.uint8)
    a[:, 20:180] = (10, 120, 30, 255)
    a[:, 100] = 0

    out = tileable(Image.fromarray(a, "RGBA"))

    assert out.width < 200 and np.asarray(out)[:, 0, 3].max() == 0
