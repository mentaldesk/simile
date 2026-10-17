from dataclasses import replace

import pytest

from simile.art.iso.lighting import SETS
from simile.art.iso.town import MODELLED, Building, Prop, Town, ground_height, shades

from .conftest import VILLAGE


@pytest.fixture(scope="module")
def town() -> Town:
    return Town(VILLAGE)


def test_the_village_has_its_buildings_and_props(town: Town) -> None:
    assert len(town.buildings) == 16
    assert len(town.props) == 93
    ids = [o.id for o in town.objects]
    assert len(ids) == len(set(ids))


def test_every_prop_kind_has_a_model(town: Town) -> None:
    assert {p.kind for p in town.props} <= MODELLED


def test_props_on_grass_stand_on_the_raised_bed(town: Town) -> None:
    for p in town.props:
        ground = town.at("ground", int(p.x), int(p.y)) or ""
        assert p.z == ground_height(ground), p.id
        assert p.z == (0.18 if ground.startswith("grass") else 0.0), p.id


def test_trees_come_in_three_shapes(town: Town) -> None:
    assert {p.variant for p in town.props if p.kind == "tree"} == {0, 1, 2}
    assert {p.variant for p in town.props if p.kind == "lamp"} == {0}


def test_a_prop_by_a_lamp_is_lit_by_it_at_night(town: Town) -> None:
    lamp = next(p for p in town.props if p.kind == "lamp")
    near = next(
        p for p in town.props if p is not lamp and abs(p.x - lamp.x) + abs(p.y - lamp.y) < 6
    )
    assert lamp in town.context(near, SETS["night"])


def test_a_building_has_a_facade_row_per_storey(town: Town) -> None:
    cafe = next(b for b in town.buildings if b.material == "cafe")
    assert cafe.id == "building-28-6"
    assert len(cafe.facade) == cafe.storeys
    assert all(len(row) == cafe.x1 - cafe.x0 for row in cafe.facade)


def test_buildings_with_an_interior_have_an_entrance_at_its_door(town: Town) -> None:
    entrances = {b.id: b.entrances for b in town.buildings if b.entrances}
    assert entrances == {"building-28-6": (3,), "building-13-6": (3,), "building-37-5": (4,)}
    for b in town.buildings:
        for col in b.entrances:
            assert (b.x0 + col, b.y1) in town.doorsteps
            assert b.facade[-1][col][0] in ("cafe_door", "shop_door")


def test_only_buildings_with_an_entrance_say_so_in_their_spec(town: Town) -> None:
    assert sum("entrances" in b.spec() for b in town.buildings) == 3


def block(x0: int, y0: int, storeys: int = 3) -> Building:
    return Building(x0, y0, x0 + 4, y0 + 4, storeys, False, "cream", (), ())


def test_a_tall_building_shades_its_neighbour_away_from_the_sun() -> None:
    evening = SETS["evening"]
    west, east = block(0, 0), block(10, 0)
    assert shades(west, east.footprint, evening)
    assert not shades(east, west.footprint, evening)


def test_a_low_sun_casts_further() -> None:
    lamp = Prop("lamp", (0, 0), 0.5, 0.5, 0.0)
    target = block(5, -2).footprint
    assert shades(lamp, target, SETS["evening"])
    assert not shades(lamp, target, SETS["afternoon"])


def test_lamps_light_nearby_buildings_only_when_they_are_on() -> None:
    lamp = Prop("lamp", (14, 2), 14.5, 2.5, 0.0)
    building = block(5, 0)
    town = Town.__new__(Town)
    town.buildings, town.props = [building], [lamp]
    assert town.context(building, SETS["night"]) == [lamp]
    assert town.context(building, replace(SETS["night"], emit={"lamp": 0.0})) == []


@pytest.mark.parametrize(
    ("tile", "metres"),
    [("grass", 0.18), ("grass_ne_nook", 0.18), ("road_line_h", -0.08), ("crosswalk_h", -0.08)]
    + [("water_s", -0.35), ("pavement", 0.0), ("plaza_inlay", 0.0), ("tactile_v", 0.0)],
)
def test_ground_heights_by_tile(tile: str, metres: float) -> None:
    assert ground_height(tile) == metres
