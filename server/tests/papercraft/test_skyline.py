import numpy as np

from simile.papercraft.skyline import APEX, plan


def test_the_apex_plan_is_a_size_flux_paints() -> None:
    image = plan("apex").image

    assert image.width % 16 == 0 and image.height % 16 == 0
    assert max(image.size) <= 1536 and image.width * image.height < 1.4e6


def test_the_towers_stand_on_the_ground_line_round_the_plans_middle() -> None:
    p = plan("apex")
    shape = np.asarray(p.shape) > 0
    xs = np.flatnonzero(shape[round(p.ground) - 2])

    assert abs((xs[0] + xs[-1]) / 2 - p.left) < 0.02 * p.image.width
    assert not shape[round(p.ground) + 2 :].any()


def test_the_tallest_spire_is_as_tall_as_its_tower_says() -> None:
    p = plan("apex")
    rows = np.flatnonzero((np.asarray(p.shape) > 0).any(axis=1))
    tallest = max(t.height + t.spire for t in APEX.towers)

    assert abs((p.ground - rows[0]) / p.ppm - tallest) < 2


def test_the_apex_is_twin_towers_joined_only_by_their_sky_bridge() -> None:
    p = plan("apex")
    shape = np.asarray(p.shape) > 0
    (bridge,) = APEX.bridges
    middle = round(p.left)

    def across(metres: float) -> bool:
        return bool(shape[round(p.ground - metres * p.ppm), middle])

    assert len(APEX.towers) == 2
    assert across(bridge.y + bridge.depth / 2)
    assert not across(bridge.y - 5) and not across(bridge.y + bridge.depth + 5)


def test_only_lit_windows_and_beacons_glow_and_all_inside_the_towers() -> None:
    p = plan("apex")
    glow, shape = np.asarray(p.glow) > 0, np.asarray(p.shape) > 0

    assert 0.01 < glow.sum() / shape.sum() < 0.2
    assert not (glow & ~shape).any()
