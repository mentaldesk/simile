from collections.abc import Callable
from datetime import UTC, datetime

from simile.player.kick import Hit, Kick, Kicks
from simile.schema import PLAYER_ID, Bionic, Body, Player, SideFacing
from simile.sim import Clock, EventBus
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
TUNNEL = Point(65, 15, "metro")
EAST, WEST = SideFacing.EAST, SideFacing.WEST

MakePackage = Callable[[dict[str, str]], str]


class Rat:
    """A stand-in for a creature, `x` tiles along the player's row."""

    def __init__(self, x: float) -> None:
        self.x = x
        self.kicks: list[Kick] = []

    def kickable(self, kick: Kick) -> Hit | None:
        ahead = (self.x - kick.at.x) * (1 if kick.facing is EAST else -1)
        if not 0 <= ahead <= kick.reach:
            return None
        return Hit(ahead, lambda: self.kicks.append(kick))


def kicks(player: Player, *rats: Rat, at: Point | None = TUNNEL) -> Kicks:
    movement = Movement(MAPS, EventBus())
    if at is not None:
        movement.track(PLAYER_ID, at)
    return Kicks(player, movement, Clock(NOW), [rat.kickable for rat in rats])


def test_a_kick_lands_on_the_nearest_thing_it_hits_the_way_they_face() -> None:
    near, far, behind = Rat(TUNNEL.x + 0.5), Rat(TUNNEL.x + 1), Rat(TUNNEL.x - 0.5)

    assert kicks(Player(), far, near, behind).kick(EAST)

    assert [len(rat.kicks) for rat in (near, far, behind)] == [1, 0, 0]
    assert near.kicks[0].strength == 1


def test_a_kick_that_hits_nothing_says_so() -> None:
    assert not kicks(Player(), Rat(TUNNEL.x + 3)).kick(EAST)
    assert not kicks(Player()).kick(WEST)


def test_the_legs_kick_harder() -> None:
    for legs, strength in [(Bionic.BIONIC_LEGS, 2), (Bionic.BIONIC_LEGS_3, 4)]:
        rat = Rat(TUNNEL.x - 1)

        assert kicks(Player(body=Body(legs=legs)), rat).kick(WEST)

        assert rat.kicks[0].strength == strength


def test_there_is_no_kick_off_a_side_view_map_or_before_they_are_anywhere() -> None:
    rat = Rat(10)

    assert not kicks(Player(), rat, at=Point(9, 10, "village")).kick(EAST)
    assert not kicks(Player(), rat, at=None).kick(EAST)
    assert rat.kicks == []
