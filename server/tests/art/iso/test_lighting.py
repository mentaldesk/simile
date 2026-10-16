import math

import pytest

from simile.art.iso.lighting import CROSSFADE_MINUTES, SETS, blend, shadow_direction, to_sun


def test_the_four_sets_and_their_hours() -> None:
    assert {name: s.hours for name, s in SETS.items()} == {
        "night": (21, 5),
        "morning": (5, 11),
        "afternoon": (11, 17),
        "evening": (17, 21),
    }


@pytest.mark.parametrize("hour", [h / 4 for h in range(96)])
def test_every_hour_has_weights_that_sum_to_one(hour: float) -> None:
    weights = blend(hour)
    assert 1 <= len(weights) <= 2
    assert sum(w for _, w in weights) == pytest.approx(1.0)


def test_outside_a_crossfade_one_set_is_drawn() -> None:
    assert blend(2.0) == [("night", 1.0)]
    assert blend(8.0) == [("morning", 1.0)]
    assert blend(14.0) == [("afternoon", 1.0)]
    assert blend(19.0) == [("evening", 1.0)]


def test_crossfades_are_centred_on_each_boundary() -> None:
    half = CROSSFADE_MINUTES / 120
    for name, s in SETS.items():
        start = s.hours[0]
        (outgoing, w_out), (incoming, w_in) = blend(start)
        assert incoming == name and outgoing != name
        assert (w_out, w_in) == pytest.approx((0.5, 0.5))
        assert blend((start - half - 0.01) % 24) == [(outgoing, 1.0)]
        assert blend((start + half + 0.01) % 24) == [(name, 1.0)]


def test_crossfade_weights_ease_in_and_out() -> None:
    (_, _), (_, quarter) = blend(16.75)
    assert quarter == pytest.approx(0.15625)


def test_shadows_fall_away_from_the_sun() -> None:
    east, north, up = to_sun(90, 30)
    assert (east, north, up) == pytest.approx((math.cos(math.radians(30)), 0, 0.5))
    assert shadow_direction(90) == pytest.approx((-1, 0))
    assert shadow_direction(180) == pytest.approx((0, -1))
    assert shadow_direction(0) == pytest.approx((0, 1))
