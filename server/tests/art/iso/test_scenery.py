import json
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from simile.art.iso import formats, scenery
from simile.art.iso.camera import project
from simile.art.iso.lighting import SETS
from simile.art.iso.town import Town
from simile.cli import create_cli

from .conftest import FakeBlender

SCENERY = Path("art") / "iso" / "scenery"


def files(content: Path) -> dict[str, float]:
    root = content / SCENERY
    return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


def manifest(content: Path, name: str = "night") -> dict:
    return json.loads((content / SCENERY / f"{name}.json").read_text())


def build(content: Path, fake: FakeBlender, **kwargs) -> list[scenery.Report]:
    return scenery.build(content, work=content.parent / "work", render=fake, **kwargs)


def test_first_build_renders_every_set(content: Path, fake_blender: FakeBlender) -> None:
    reports = build(content, fake_blender)

    assert [r.name for r in reports] == list(SETS)
    assert len(fake_blender.jobs) == 4
    for name in SETS:
        m = manifest(content, name)
        images = [c["image"] for c in m["ground"]["chunks"]]
        images += [m["light_map"]["image"], *(o["image"] for o in m["objects"])]
        assert all((content / SCENERY / image).exists() for image in images)


def test_a_second_build_renders_and_writes_nothing(
    content: Path, fake_blender: FakeBlender
) -> None:
    build(content, fake_blender)
    before = files(content)
    fake_blender.jobs.clear()

    reports = build(content, fake_blender)

    assert fake_blender.jobs == []
    assert all(not r.rendered and not r.written and not r.removed for r in reports)
    assert files(content) == before


def test_changing_a_prop_renders_only_what_it_touches(
    content: Path, fake_blender: FakeBlender
) -> None:
    build(content, fake_blender, sets=["evening"])
    town = Town(content / "map" / "village.tmj")
    before = scenery.plan(town, SETS["evening"])
    fake_blender.jobs.clear()
    path = content / "map" / "village.tmj"
    data = json.loads(path.read_text())
    decor = next(layer for layer in data["layers"] if layer["name"] == "decor")
    lamp = next(p for p in town.props if p.kind == "lamp")
    decor["data"][lamp.tile[1] * data["width"] + lamp.tile[0]] = 0
    path.write_text(json.dumps(data))

    build(content, fake_blender, sets=["evening"])

    after = scenery.plan(Town(path), SETS["evening"])
    changed = {k for k in after.sprites if after.sprites[k].hash != before.sprites[k].hash}
    [job] = fake_blender.jobs
    assert {t["key"] for t in job["sprites"]} == changed
    assert lamp.id not in after.sprites
    assert job.get("ground") and job.get("lightmap")


def test_force_renders_everything(content: Path, fake_blender: FakeBlender) -> None:
    build(content, fake_blender, sets=["morning"])
    fake_blender.jobs.clear()

    build(content, fake_blender, sets=["morning"], force=True)

    [job] = fake_blender.jobs
    assert len(job["sprites"]) == len(manifest(content, "morning")["objects"])


def test_a_missing_image_is_rendered_again(content: Path, fake_blender: FakeBlender) -> None:
    build(content, fake_blender, sets=["night"])
    fake_blender.jobs.clear()
    tree = next(o for o in manifest(content)["objects"] if o["kind"] == "tree")
    (content / SCENERY / tree["image"]).unlink()

    build(content, fake_blender, sets=["night"])

    [job] = fake_blender.jobs
    assert [t["key"] for t in job["sprites"]] == [tree["id"]]
    assert "ground" not in job


def test_files_nothing_uses_are_removed(content: Path, fake_blender: FakeBlender) -> None:
    build(content, fake_blender, sets=["night"])
    stray = content / SCENERY / "night" / "old-sprite.webp"
    stray.write_bytes(b"x")

    report = build(content, fake_blender, sets=["night"])[0]

    assert not stray.exists()
    assert report.removed == ["night/old-sprite.webp"]


def test_objects_hang_from_their_anchor(content: Path, fake_blender: FakeBlender) -> None:
    build(content, fake_blender, sets=["afternoon"])
    m = manifest(content, "afternoon")
    town = Town(content / "map" / "village.tmj")
    on_grass = next(p for p in town.props if p.z > 0)
    by_id = {o["id"]: o for o in m["objects"]}

    obj = by_id[on_grass.id]
    ax, ay = project(on_grass.x, on_grass.y)
    assert obj["anchor"] == [on_grass.x, on_grass.y]
    assert obj["offset"] == [-12 - round(ax), -36 - round(ay)]
    assert sum(s["width"] for s in obj["slices"]) == obj["width"]


def test_sprites_are_stored_in_the_sprite_format(content: Path, fake_blender: FakeBlender) -> None:
    build(content, fake_blender, sets=["night"])
    m = manifest(content)
    assert all(o["image"].endswith(f".{formats.SPRITES.ext}") for o in m["objects"])
    assert all(c["image"].endswith(f".{formats.GROUND.ext}") for c in m["ground"]["chunks"])
    with Image.open(content / SCENERY / m["light_map"]["image"]) as light:
        assert light.mode == "RGB"
        assert light.size == (m["map"]["width"] * 8, m["map"]["height"] * 16)
    assert m["light_map"]["sun_y"] == m["light_map"]["height"] == m["map"]["height"] * 8


def test_ground_under_a_building_is_the_ground_without_it(
    content: Path, fake_blender: FakeBlender
) -> None:
    build(content, fake_blender, sets=["night"])
    m = manifest(content)
    building = next(o for o in m["objects"] if o["kind"] == "building")
    x0, y0, x1, y1 = building["footprint"]
    inside = project((x0 + x1) / 2, (y0 + y1) / 2)
    outside = project(x0 - 2, y0 - 2)
    assert ground_pixel(content, m, *inside) == (150, 160, 170)
    assert ground_pixel(content, m, *outside) == (90, 100, 110)


def ground_pixel(content: Path, m: dict, sx: float, sy: float) -> tuple[int, ...]:
    for chunk in m["ground"]["chunks"]:
        x, y = round(sx) - chunk["x"], round(sy) - chunk["y"]
        if 0 <= x < chunk["width"] and 0 <= y < chunk["height"]:
            with Image.open(content / SCENERY / chunk["image"]) as image:
                return tuple(round(c / 10) * 10 for c in image.convert("RGB").getpixel((x, y)))
    raise AssertionError("off the ground")


def test_the_manifest_lists_ground_heights(content: Path, fake_blender: FakeBlender) -> None:
    build(content, fake_blender, sets=["night"])
    m = manifest(content)
    assert m["ground"]["heights"] == {
        "grass": 0.18,
        "water": -0.35,
        "road": -0.08,
        "crosswalk": -0.08,
    }
    assert m["tile"]["px_per_metre_up"] == pytest.approx(53.44, abs=0.01)


def test_the_command_renders_the_sets_it_is_given(
    content: Path, fake_blender: FakeBlender, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scenery, "blender_renderer", fake_blender)
    args = ["art", "iso", "scenery", "--set", "night", "--content", str(content)]

    result = CliRunner().invoke(create_cli(), args)

    assert result.exit_code == 0, result.output
    assert result.output.startswith("night: rendered")
    assert [job["light"]["name"] for job in fake_blender.jobs] == ["night"]


def test_the_command_rejects_unknown_sets(content: Path) -> None:
    args = ["art", "iso", "scenery", "--set", "dusk", "--content", str(content)]
    result = CliRunner().invoke(create_cli(), args)
    assert result.exit_code != 0
    assert "dusk" in result.output
