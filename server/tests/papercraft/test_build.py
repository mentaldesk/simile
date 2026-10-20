import colorsys
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


def test_a_tiled_paper_joins_itself_without_a_step_where_its_light_falls_off() -> None:
    rng = np.random.default_rng(0)
    falloff = np.linspace(200, 140, 400)[None, :, None]
    painted = falloff + rng.normal(0, 2, (200, 400, 3))
    paper = Image.fromarray(np.clip(painted, 0, 255).astype(np.uint8))

    tiled = np.asarray(tileable(paper), dtype=np.float32)
    columns = np.tile(tiled.mean(axis=(0, 2)), 2)
    smooth = np.convolve(columns, np.ones(8) / 8, mode="valid")

    assert np.abs(np.diff(smooth)).max() < 0.6


def test_levelling_keeps_a_tiles_mean_brightness_and_its_colours_hues() -> None:
    falloff = np.linspace(1.0, 0.7, 400)[None, :, None]
    painted = np.broadcast_to(np.array([150.0, 20.0, 35.0]), (40, 400, 3)) * falloff
    gold = np.array([181.0, 160.0, 103.0])
    painted[:, 150:160] = gold * falloff[:, 150:160]
    tile, after, start = painted[:, :300], painted[:, 300:332], painted[:, :32]

    levelled = build_module._level(tile, after, start)

    luma = np.array([0.299, 0.587, 0.114])
    assert abs((levelled @ luma).mean() - (tile @ luma).mean()) < 1.5
    hues = [
        [colorsys.rgb_to_hsv(*(pixel / 255))[0] for pixel in stripe[:, 150:160].reshape(-1, 3)]
        for stripe in (tile, levelled)
    ]
    assert np.allclose(hues[0], hues[1], atol=0.002)


def test_a_tiled_sky_is_not_joined_through_a_cloud() -> None:
    x = np.arange(600)[None, :]
    y = np.arange(80)[:, None]
    sky = np.repeat((150 - 50 * x / 600 + 30 * y / 80)[..., None], 3, axis=2)
    sky[15:55, 20:90] = 255
    sky[15:55, 520:590] = 255

    tiled = np.asarray(tileable(Image.fromarray(sky.astype(np.uint8)), plain=True), np.float32)
    cloud = (tiled[35] - tiled[70]).mean(axis=1) > 40
    edges = np.flatnonzero(np.diff(np.r_[0, cloud.astype(int), 0]))
    widths = edges[1::2] - edges[::2]

    assert all(69 <= w <= 71 for w in widths)


def test_a_layer_with_a_gap_near_each_end_is_cut_at_the_gaps() -> None:
    a = np.zeros((40, 200, 4), dtype=np.uint8)
    a[:, 20:180] = (10, 120, 30, 255)
    a[:, 100] = 0

    out = tileable(Image.fromarray(a, "RGBA"))

    assert out.width < 200 and np.asarray(out)[:, 0, 3].max() == 0
