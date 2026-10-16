import pytest

from simile.art.iso.camera import project
from simile.art.iso.depth import SLICE_PX, front, slices

BUILDING = (10.0, 4.0, 16.0, 8.0)


def feet(x: float, y: float) -> float:
    return project(x, y)[1]


def key_at(footprint: tuple[float, float, float, float], x: float, y: float) -> float:
    sx, _ = project(x, y)
    left = int(project(footprint[0], footprint[3])[0]) - 200
    for s in slices(footprint, left, 800):
        if s["x"] <= sx - left < s["x"] + s["width"]:
            return s["depth"]
    raise AssertionError("no slice under the resident")


@pytest.mark.parametrize("spot", [(11.0, 8.5), (13.0, 9.0), (15.5, 8.4), (16.4, 5.0), (17.0, 7.5)])
def test_residents_south_or_east_of_a_building_are_drawn_in_front(spot) -> None:
    assert feet(*spot) > key_at(BUILDING, *spot)


@pytest.mark.parametrize("spot", [(11.0, 3.5), (15.0, 3.0), (9.5, 5.0), (9.0, 7.5)])
def test_residents_north_or_west_of_a_building_are_drawn_behind(spot) -> None:
    assert feet(*spot) < key_at(BUILDING, *spot)


def test_one_key_alone_gets_the_south_wall_wrong() -> None:
    near_corner_key = project(16, 8)[1]
    in_front_of_west_end = feet(10.5, 8.5)
    assert in_front_of_west_end < near_corner_key


def test_slices_cover_the_sprite_once() -> None:
    parts = slices(BUILDING, -37, 500)
    assert parts[0]["x"] == 0
    for a, b in zip(parts, parts[1:], strict=False):
        assert a["x"] + a["width"] == b["x"]
    assert parts[-1]["x"] + parts[-1]["width"] == 500


def test_slices_follow_the_diagonal_grid() -> None:
    parts = slices(BUILDING, -37, 500)
    for s in parts[1:]:
        assert (s["x"] - 37) % SLICE_PX == 0


def test_a_point_has_one_slice() -> None:
    assert slices((5.5, 7.5, 5.5, 7.5), -40, 120) == [
        {"x": 0, "width": 120, "depth": project(5.5, 7.5)[1]}
    ]


def test_the_front_edge_runs_along_the_south_and_east_walls() -> None:
    assert front(BUILDING, 2.0) == project(10, 8)[1]
    assert front(BUILDING, 8.0) == project(16, 8)[1]
    assert front(BUILDING, 12.0) == project(16, 4)[1]
    assert front(BUILDING, 30.0) == front(BUILDING, 12.0)
