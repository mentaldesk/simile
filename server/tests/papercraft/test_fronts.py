import numpy as np
import pytest

from simile.papercraft.fronts import GREY, UNIT, Box, Front, backdrop, draw, unit_plans, units
from simile.papercraft.layout import Facade, Mural, load_layout
from simile.papercraft.village import LOOKS, STREETS, TILE, front

LAYOUT = load_layout()
FRONTS = {building: front(f, LOOKS[building]) for building, f in LAYOUT.facades.items()}


def overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("building", FRONTS)
def test_every_opening_is_on_the_wall_and_clear_of_the_others_and_the_murals(
    building: str,
) -> None:
    f = FRONTS[building]
    openings = [*f.window_boxes(), *f.shop_boxes()]

    assert openings or f.murals
    for box in openings:
        assert box[0] > 0 and box[2] < f.width and box[3] < f.wall_height
        assert not (f.door_box and overlaps(box, f.door_box))
        assert not any(overlaps(box, mural) for mural in f.murals)
    for i, a in enumerate(openings):
        assert not any(overlaps(a, b) for b in openings[i + 1 :])


@pytest.mark.parametrize("building", FRONTS)
def test_a_front_is_as_wide_and_tall_as_its_building_on_the_map(building: str) -> None:
    facade, f = LAYOUT.facades[building], FRONTS[building]

    assert f.width == pytest.approx(facade.width * TILE)
    assert f.wall_height == pytest.approx(facade.height * TILE)
    if facade.door is not None:
        assert f.door == pytest.approx((facade.door + 0.5) * TILE)
    assert f.door_box and not any(overlaps(f.door_box, mural) for mural in f.murals)


@pytest.mark.parametrize("building", FRONTS)
def test_a_plan_glows_only_on_its_walls(building: str) -> None:
    f = FRONTS[building]
    plan = draw(f)
    ys, xs = np.nonzero(np.asarray(plan.glow) > 0)

    assert len(xs)
    assert xs.min() >= plan.left - 1
    assert xs.max() <= plan.left + f.width * plan.ppm + 1
    assert ys.max() <= plan.ground + 1
    assert ys.min() >= plan.ground - f.wall_height * plan.ppm - 1


@pytest.mark.parametrize("building", FRONTS)
def test_a_front_is_painted_as_units_of_a_size_flux_keeps_to(building: str) -> None:
    f = FRONTS[building]
    parts = unit_plans(f)

    for (x, plan), (_, unit) in zip(parts, units(f), strict=True):
        width, height = plan.image.size
        assert width % 16 == 0 and height % 16 == 0 and max(width, height) <= 1536
        assert 0.8e6 < width * height < 1.4e6
        assert unit.width <= UNIT
        assert unit.door is None or f.door == pytest.approx(x + unit.door)
    assert sum(unit.width for _, unit in units(f)) == pytest.approx(f.width)
    assert sum(unit.door is not None for _, unit in units(f)) == (f.door is not None)


def test_a_mural_wall_is_left_blank_between_its_storeys() -> None:
    facade = Facade("shop", "high_street", 0, 6, 11, 3, False, None, (Mural(1, 4, 0.7, 2.85),))
    f = front(facade, LOOKS["corner_shop"])

    (mural,) = f.murals
    assert mural == pytest.approx((1.1, 0.7 * 4.4, 5.5, 11 * TILE - 0.3))
    assert f.shop_boxes() and not any(overlaps(b, mural) for b in f.window_boxes())
    assert f.door_box and not overlaps(f.door_box, mural)


def test_a_white_building_is_drawn_on_grey() -> None:
    assert backdrop(FRONTS["gallery"]) == GREY
    assert draw(FRONTS["gallery"]).image.getpixel((0, 0)) == GREY
    assert backdrop(FRONTS["coffee_shop"]) != GREY


def test_every_building_and_street_on_the_maps_has_a_look() -> None:
    assert set(LAYOUT.facades) <= set(LOOKS)
    assert set(LAYOUT.streets) <= set(STREETS)
    assert all(isinstance(f, Front) for f in FRONTS.values())
