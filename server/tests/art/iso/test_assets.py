import json
from pathlib import Path

import pytest
from PIL import Image

from simile.art.iso import camera, depth, formats, scenery
from simile.art.iso.interior import find
from simile.art.iso.lighting import INSIDE, SETS
from simile.art.iso.town import GROUND_HEIGHTS, Town

ISO = scenery.CONTENT_DIR / "art" / "iso"
SCENERY = ISO / "scenery"
BUDGET_BYTES = 40_000_000
STALE = "content/art/iso is out of date: run `cd server && uv run simile art iso scenery`"
PINNED_SOURCES = "70a2a376919ff8e2"


def load(name: str) -> dict:
    return json.loads((SCENERY / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def manifests() -> dict[str, dict]:
    return {name: load(name) for name in SETS}


def test_iso_art_fits_the_budget() -> None:
    total = sum(p.stat().st_size for p in ISO.rglob("*") if p.is_file())
    assert total < BUDGET_BYTES, f"content/art/iso is {total / 1e6:.1f} MB, over the 40 MB budget"


def test_each_set_has_a_manifest_and_nothing_else_is_there() -> None:
    expected = {f"{name}.json" for name in SETS} | set(SETS)
    assert {p.name for p in SCENERY.iterdir()} == expected


@pytest.mark.parametrize("name", list(SETS))
def test_every_image_in_a_manifest_is_there_at_its_size(name: str) -> None:
    m = load(name)
    for obj in m["objects"]:
        with Image.open(SCENERY / obj["image"]) as image:
            assert image.size == (obj["width"], obj["height"]), obj["image"]
            assert image.mode == "RGBA", obj["image"]
    for chunk in m["ground"]["chunks"]:
        with Image.open(SCENERY / chunk["image"]) as image:
            assert image.size == (chunk["width"], chunk["height"]), chunk["image"]
    light = m["light_map"]
    with Image.open(SCENERY / light["image"]) as image:
        assert image.mode == "RGB"
        assert image.size == (light["width"], light["sun_y"] + light["height"])
        assert (light["width"], light["height"]) == (m["map"]["width"] * 8, m["map"]["height"] * 8)


@pytest.mark.parametrize("name", list(SETS))
def test_images_use_the_format_for_their_kind(name: str) -> None:
    m = load(name)
    assert all(o["image"].endswith(f".{formats.SPRITES.ext}") for o in m["objects"])
    assert all(c["image"].endswith(f".{formats.GROUND.ext}") for c in m["ground"]["chunks"])
    assert m["light_map"]["image"].endswith(f".{formats.LIGHT_MAP.ext}")


@pytest.mark.parametrize("name", list(SETS))
def test_ground_chunks_cover_the_ground_once(name: str) -> None:
    g = load(name)["ground"]
    assert sum(c["width"] * c["height"] for c in g["chunks"]) == g["width"] * g["height"]
    for c in g["chunks"]:
        assert g["x"] <= c["x"] and c["x"] + c["width"] <= g["x"] + g["width"]
        assert g["y"] <= c["y"] and c["y"] + c["height"] <= g["y"] + g["height"]
        assert c["width"] <= 2048 and c["height"] <= 2048


def test_every_set_has_the_same_objects_in_the_same_places(manifests: dict[str, dict]) -> None:
    def placing(m: dict) -> list:
        return [{k: v for k, v in o.items() if k not in ("image", "hash")} for o in m["objects"]]

    first, *rest = manifests.values()
    for m in rest:
        assert placing(m) == placing(first), m["set"]


def test_slices_cover_each_sprite(manifests: dict[str, dict]) -> None:
    m = manifests["night"]
    for obj in m["objects"]:
        xs = [(s["x"], s["width"]) for s in obj["slices"]]
        assert xs[0][0] == 0 and sum(w for _, w in xs) == obj["width"], obj["id"]


def test_manifests_describe_their_set(manifests: dict[str, dict]) -> None:
    for name, m in manifests.items():
        assert m["set"] == name
        assert tuple(m["hours"]) == SETS[name].hours
        assert m["sun"] == {"azimuth": SETS[name].azimuth, "elevation": SETS[name].elevation}


def test_renders_are_up_to_date_with_the_map_and_the_pipeline(
    manifests: dict[str, dict],
) -> None:
    town = Town(scenery.CONTENT_DIR / "map" / "village.tmj")
    for name, m in manifests.items():
        plan = scenery.plan(town, SETS[name])
        assert m["ground"]["hash"] == plan.ground_hash, STALE
        assert m["light_map"]["hash"] == plan.light_map_hash, STALE
        assert [o["id"] for o in m["objects"]] == [o.id for o in town.objects], STALE
        assert [o["hash"] for o in m["objects"]] == [
            plan.sprites[o.id].hash for o in town.objects
        ], STALE
        assert m["ground"]["heights"] == GROUND_HEIGHTS, STALE
        for o in m["objects"]:
            left = round(camera.project(*o["anchor"])[0]) + o["offset"][0]
            assert o["slices"] == depth.slices(o["footprint"], left, o["width"]), STALE


def test_the_pipeline_code_is_pinned() -> None:
    changed = (
        "The scenery pipeline's code changed. If renders would change, bump PIPELINE_VERSION in "
        "simile/art/iso/scenery.py and rerun `uv run simile art iso scenery`; either way, update "
        "the pin here."
    )
    assert scenery.sources_digest() == PINNED_SOURCES, changed


def test_the_ground_under_buildings_is_lit(manifests: dict[str, dict]) -> None:
    m = manifests["afternoon"]
    for building in (o for o in m["objects"] if o["kind"] == "building"):
        x0, y0, x1, y1 = building["footprint"]
        sx, sy = camera.project((x0 + x1) / 2, (y0 + y1) / 2)
        chunk = next(
            c
            for c in m["ground"]["chunks"]
            if c["x"] <= sx < c["x"] + c["width"] and c["y"] <= sy < c["y"] + c["height"]
        )
        with Image.open(SCENERY / chunk["image"]) as image:
            pixel = image.convert("RGB").getpixel((round(sx) - chunk["x"], round(sy) - chunk["y"]))
        assert sum(pixel) > 150, (building["id"], pixel)


def test_committed_files_are_all_in_a_manifest(manifests: dict[str, dict]) -> None:
    used = set()
    for m in manifests.values():
        used |= {o["image"] for o in m["objects"]}
        used |= {c["image"] for c in m["ground"]["chunks"]}
        used.add(m["light_map"]["image"])
    on_disk = {
        str(p.relative_to(SCENERY))
        for p in SCENERY.rglob("*")
        if p.is_file() and p.parent != SCENERY
    }
    assert on_disk == used


def test_paths_are_relative_to_the_manifest(manifests: dict[str, dict]) -> None:
    for name, m in manifests.items():
        assert all(Path(o["image"]).parts[0] == name for o in m["objects"])


INTERIORS = ISO / "interiors"
ROOMS = {room.id: room for room in find(scenery.CONTENT_DIR)}


@pytest.fixture(scope="module")
def rooms() -> dict[str, dict]:
    return {name: json.loads((INTERIORS / f"{name}.json").read_text()) for name in ROOMS}


def images(m: dict) -> list[str]:
    return [
        *(c["image"] for c in m["ground"]["chunks"]),
        m["light_map"]["image"],
        *(o["image"] for o in m["objects"]),
    ]


def test_each_interior_has_a_manifest_and_nothing_else_is_there() -> None:
    expected = {f"{name}.json" for name in ROOMS} | set(ROOMS)
    assert {p.name for p in INTERIORS.iterdir()} == expected


def test_interiors_are_up_to_date_with_their_maps_and_the_pipeline(rooms: dict[str, dict]) -> None:
    for name, m in rooms.items():
        room = ROOMS[name]
        plan = scenery.plan(room, INSIDE)
        assert (m["set"], m["map"]["id"]) == ("inside", name)
        assert m["ground"]["hash"] == plan.ground_hash, STALE
        assert m["light_map"]["hash"] == plan.light_map_hash, STALE
        assert [o["id"] for o in m["objects"]] == [o.id for o in room.objects], STALE
        assert [o["hash"] for o in m["objects"]] == [
            plan.sprites[o.id].hash for o in room.objects
        ], STALE
        for o in m["objects"]:
            left = round(camera.project(*o["anchor"])[0]) + o["offset"][0]
            assert o["slices"] == depth.slices(o["footprint"], left, o["width"]), STALE


def test_every_image_in_an_interior_is_there_at_its_size(rooms: dict[str, dict]) -> None:
    for name, m in rooms.items():
        for o in m["objects"]:
            with Image.open(INTERIORS / o["image"]) as image:
                assert image.size == (o["width"], o["height"]), o["image"]
                assert image.mode == "RGBA", o["image"]
        for chunk in m["ground"]["chunks"]:
            with Image.open(INTERIORS / chunk["image"]) as image:
                assert image.size == (chunk["width"], chunk["height"]), chunk["image"]
        light = m["light_map"]
        with Image.open(INTERIORS / light["image"]) as image:
            assert image.size == (light["width"], light["sun_y"] + light["height"])
        assert all(Path(image).parts[0] == name for image in images(m))
        assert all(image.endswith(".webp") for image in images(m))


def test_committed_interior_files_are_all_in_a_manifest(rooms: dict[str, dict]) -> None:
    used = {image for m in rooms.values() for image in images(m)}
    on_disk = {
        str(p.relative_to(INTERIORS))
        for p in INTERIORS.rglob("*")
        if p.is_file() and p.parent != INTERIORS
    }
    assert on_disk == used


def test_frames_are_empty_inside_their_canvas(rooms: dict[str, dict]) -> None:
    frames = [o for o in rooms["gallery"]["objects"] if o["kind"] == "frame"]
    assert len(frames) == 13
    for frame in frames:
        xs = [x for x, _ in frame["canvas"]]
        ys = [y for _, y in frame["canvas"]]
        assert 0 < min(xs) < max(xs) < frame["width"] and 0 < min(ys) < max(ys) < frame["height"]
        middle = (round(sum(xs) / 4), round(sum(ys) / 4))
        with Image.open(INTERIORS / frame["image"]) as image:
            assert image.getchannel("A").getpixel(middle) == 0, frame["id"]
            assert image.getchannel("A").getextrema()[1] == 255, frame["id"]
