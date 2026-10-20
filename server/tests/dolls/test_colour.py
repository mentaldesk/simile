import numpy as np
import pytest

from simile.art.palette import PALETTE
from simile.dolls.colour import KNEE, delta_e, delta_e_lab, hex_of, muted, oklab, rgb

SHARMA = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
]


@pytest.mark.parametrize(("a", "b", "expected"), SHARMA)
def test_ciede2000_matches_sharmas_reference_pairs(a, b, expected) -> None:
    assert delta_e_lab(a, b) == pytest.approx(expected, abs=1e-4)


def test_hex_round_trips() -> None:
    assert hex_of(rgb("#2ce8f5")) == "#2ce8f5"


@pytest.mark.parametrize("name", PALETTE)
def test_muting_keeps_lightness_and_hue_and_stays_close(name: str) -> None:
    colour = rgb(PALETTE[name])
    quiet = muted(colour)
    before, after = oklab(colour), oklab(quiet)

    assert delta_e(colour, quiet) < 9
    assert after[0] == pytest.approx(before[0], abs=0.01)
    if np.hypot(before[1], before[2]) > KNEE:
        hue = np.degrees(np.arctan2(before[2], before[1]) - np.arctan2(after[2], after[1]))
        assert abs((hue + 180) % 360 - 180) < 2
        assert np.hypot(after[1], after[2]) < np.hypot(before[1], before[2])


def test_quiet_colours_are_left_alone() -> None:
    for name in ("ink", "slate", "pavement", "cream", "espresso", "white"):
        assert muted(rgb(PALETTE[name])) == rgb(PALETTE[name])
