import json
import re
from dataclasses import replace

import pytest

from simile.papercraft import catalogue
from simile.papercraft.build import CONTENT, MANIFEST
from simile.papercraft.catalogue import (
    EXTRAS,
    FURNITURE,
    PLATFORMS,
    WORDS,
    Moulding,
    index,
    landmarks,
    paintings,
)
from simile.papercraft.layout import STREET_DIR, _objects, _props, load_layout
from simile.papercraft.painter import CLEAN, in_style
from simile.papercraft.village import (
    GROUNDS,
    LOOKS,
    PAPER_STYLES,
    STREETS,
    TILE,
    UNDERGROUND,
    Landmark,
    papers,
)

LAYOUT = load_layout()
PIECES = {p.key: p for p in paintings(LAYOUT)}
MANIFEST_JSON = json.loads((CONTENT / MANIFEST).read_text())
GRIME = re.compile(
    r"\b(grime|grimy|dirt|dirty|smudges?|smudged|stains?|stained|slime|slimy|rust|rusty|rusted|"
    r"scuffs?|scuffed|worn(?! dip pen)|wear|damp|filth|filthy|soot|sooty|mouldy|cracked|chipped|"
    r"battered|dented)\b",
    re.IGNORECASE,
)
OVERHANG = {"tree", "palm_tree", "tunnel_arch"}
"""Pieces whose crowns or arches spread well past their cells, as drawn today."""
SLACK = 0.6
"""Metres past its cells a piece may reach: the most today's other art does."""


def underground_furniture() -> set[str]:
    """The map furniture that only maps under the village use."""
    under, over = set(), set()
    for path in sorted(STREET_DIR.rglob("*.tmj")):
        data = json.loads(path.read_text())
        below = path.stem in UNDERGROUND or _props(data).get("street") in UNDERGROUND
        (under if below else over).update(o["name"] for o in _objects(data, "furniture"))
    return under - over


def underground_pieces() -> set[str]:
    """Every piece only the streets under the village use. The extras dress any room, so
    aren't among them."""
    keys = {
        f"layers/{getattr(STREETS[street], name)}"
        for street in UNDERGROUND
        for name in ("sky", "far", "mid", "near", "ground", "foreground")
    }
    for building, facade in LAYOUT.facades.items():
        if facade.street in UNDERGROUND:
            keys |= {f"fronts/{building}", f"glow/{building}"}
            keys |= {f"papers/{p}" for p in papers(LAYOUT).get(building, [])}
    for name in underground_furniture() & set(FURNITURE):
        spec = FURNITURE[name]
        keys.add(f"{spec.folder}/{name}")
        keys |= {f"{spec.folder}/{name}-{v}" for v in spec.variants}
    return keys


def style_of(key: str) -> str:
    """The style a piece is painted in, from what it's made from."""
    folder, name = key.split("/", 1)
    if folder in ("fronts", "glow"):
        return LOOKS[name].style
    if folder == "papers":
        prompt = PIECES[key].prompt
        lead = next(s for s, w in WORDS.items() if prompt.startswith((w.lead, w.paper_lead)))
        assert key == "papers/slab" or lead == PAPER_STYLES[name]
        return lead
    if folder == "layers":
        return next(s for s, w in WORDS.items() if PIECES[key].prompt.startswith(w.lead))
    specs = {**FURNITURE, **EXTRAS, **PLATFORMS}
    return specs[name if name in specs else name.rsplit("-", 1)[0]].style


def test_the_maps_under_the_village_use_some_furniture_of_their_own() -> None:
    assert {"train_carriage", "sewer_walkway", "pipes"} <= underground_furniture()


@pytest.mark.parametrize("key", sorted(underground_pieces()))
def test_every_underground_piece_is_cartoon_or_grimy(key: str) -> None:
    assert style_of(key) in ("cartoon", "grimy")


def test_every_village_front_is_clean_with_todays_details() -> None:
    village = {b for b, f in LAYOUT.facades.items() if f.street not in UNDERGROUND}

    assert {b for b in village if LOOKS[b].style != "clean" or not LOOKS[b].modern} == set()
    assert FURNITURE["metro_entrance"].style == "clean"


def test_every_village_sprite_is_clean() -> None:
    village = (set(LAYOUT.furniture) - underground_furniture()) | set(EXTRAS) | set(PLATFORMS)
    specs = {**FURNITURE, **EXTRAS, **PLATFORMS}

    assert {name for name in village if specs[name].style != "clean"} == set()


@pytest.mark.parametrize("key", sorted(set(PIECES) - underground_pieces()))
def test_no_village_prompt_has_a_grime_word(key: str) -> None:
    piece = PIECES[key]

    for prompt in (piece.prompt, *piece.prompts):
        assert not GRIME.findall(prompt)


def test_the_clean_style_has_no_grime_word() -> None:
    clean = WORDS["clean"]
    for words in (CLEAN, clean.lead, clean.redraw, clean.texture, clean.front, clean.paper_lead):
        assert not GRIME.findall(words)


@pytest.mark.parametrize("style", WORDS)
def test_every_style_has_its_own_words(style: str) -> None:
    words = WORDS[style]

    assert "{subject}" in words.redraw and "{back}" in words.redraw
    assert "{}" in words.texture
    assert in_style("A teapot.", style).startswith("A teapot. Art style: ")
    others = [w for s, w in WORDS.items() if s != style]
    assert all(words.lead != w.lead and words.front != w.front for w in others)


@pytest.mark.parametrize(
    "name",
    sorted(
        n
        for n in LAYOUT.furniture
        if n in FURNITURE and not FURNITURE[n].stretch and n not in OVERHANG
    ),
)
def test_every_furniture_piece_fits_its_largest_cells(name: str) -> None:
    spec = FURNITURE[name]
    width = MANIFEST_JSON["pieces"][f"{spec.folder}/{name}"]["size"][0] / MANIFEST_JSON["ppm"]

    assert width <= LAYOUT.furniture[name][0] * TILE + SLACK


def test_the_manifest_carries_the_measurements_of_the_comic_art() -> None:
    furniture = index(LAYOUT)["furniture"]

    assert {n: f["seat"] for n, f in furniture.items() if "seat" in f} == {
        "stool": 0.567,
        "bench": 0.408,
        "cafe_table": 0.5,
        "noodle_table": 0.542,
        "table": 0.492,
    }
    assert {n: f["bed"] for n, f in furniture.items() if "bed" in f} == {"bed": 0.492}
    assert {n: f["light"] for n, f in furniture.items() if "light" in f} == {"lamp": 3.31}
    assert furniture["picture_frame"]["moulding"] == Moulding(14, 15, 13, 14)._asdict()
    assert {n: f for n, f in MANIFEST_JSON["furniture"].items()} == furniture


def test_a_street_with_a_city_lists_it_between_the_sky_and_the_far_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    high = STREETS["high_street"]
    monkeypatch.setitem(STREETS, "high_street", replace(high, city="city-apex"))

    layers = index(LAYOUT)["streets"]

    assert list(layers["high_street"])[:3] == ["sky", "city", "far"]
    assert layers["high_street"]["city"] == "layers/city-apex"
    assert all("city" not in layers[s] for s in UNDERGROUND)
    assert "city" in index(LAYOUT)["parallax"]


def test_every_village_layer_and_paper_is_clean() -> None:
    village = {k for k in PIECES if k.startswith(("layers/", "papers/"))} - underground_pieces()

    assert {k for k in village if style_of(k) != "clean"} == set()
    assert len(village) == 32


def test_every_street_above_ground_has_the_city_and_the_apex_over_its_square() -> None:
    listed = index(LAYOUT)
    above = sorted(set(STREETS) - UNDERGROUND)

    assert {s: listed["streets"][s].get("city") for s in above} == dict.fromkeys(
        above, "layers/city"
    )
    assert listed["landmarks"]["apex"]["at"] == dict.fromkeys(above, 0.6)
    assert [p.key for p in landmarks()] == ["landmarks/apex", "glow/apex"]


def test_the_far_layers_stay_hills_or_river_with_room_above_for_the_city() -> None:
    for street in set(STREETS) - UNDERGROUND:
        far = PIECES[f"layers/{STREETS[street].far}"]
        assert far.headroom > 0.3
        assert "no towers" in far.prompt.lower()
    assert "no spires" in PIECES["layers/city"].prompt.lower()


def test_the_village_ground_strips_are_banded_and_measured() -> None:
    grounds = {f"layers/{STREETS[s].ground}" for s in set(STREETS) - UNDERGROUND}
    grounds |= {f"layers/{key}" for key in GROUNDS.values()}

    for key in grounds:
        assert "banded" in PIECES[key].cut and PIECES[key].surface is not None
        assert MANIFEST_JSON["pieces"][key]["surface"] == PIECES[key].surface


def test_a_landmark_is_listed_with_its_glow_and_where_it_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apex = Landmark("the Apex towers", 40.0, {"high_street": 0.6})
    monkeypatch.setitem(catalogue.LANDMARKS, "apex", apex)

    day, night = landmarks()

    assert (day.key, day.kind, day.landmark) == ("landmarks/apex", "landmark", "apex")
    assert (night.key, night.kind, night.base) == ("glow/apex", "glow", day.key)
    assert index(LAYOUT)["landmarks"] == {
        "apex": {"piece": "landmarks/apex", "glow": "glow/apex", "at": {"high_street": 0.6}}
    }
    assert not GRIME.findall(day.prompt + night.prompt)
