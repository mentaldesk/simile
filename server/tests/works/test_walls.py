from datetime import timedelta

import pytest

from simile.behaviour import MuralSpot
from simile.memory import MemoryStore
from simile.protocol import Artist, Mural, MuralsMessage, Wall
from simile.schema import Npc, Relationship
from simile.sim import Clock
from simile.social import meet
from simile.works import WorksStore
from simile.works.walls import Walls, boldness, readiness
from simile.world.movement import Point

from .conftest import MEI, NOW, OTHER_WALL, SUKI, VIKTOR, WALL, mural

NPCS = {npc.id: npc for npc in (VIKTOR, SUKI, MEI)}
STRANGER, LIKED, RIVAL, FRIEND = 0.0, 0.3, -0.5, 0.6


def feeling(owner: Npc, about: str, level: float) -> Relationship:
    return meet(owner, about).model_copy(
        update={"like": level, "trust": level, "respect": level, "familiarity": 0.8}
    )


def ready(painter: Npc, hours_ago: float, fondness: float = STRANGER, artist: str = "x") -> float:
    score = readiness(painter, mural("m", artist, hours_ago=hours_ago), fondness, NOW)
    assert score is not None
    return score


def walls(
    works: WorksStore,
    memory: MemoryStore,
    positions: dict[str, Point] | None = None,
    painting: dict[str, str] | None = None,
) -> Walls:
    return Walls(
        [WALL, OTHER_WALL],
        works,
        memory,
        Clock(NOW),
        NPCS,
        positions=lambda: positions or {},
        painting=lambda: painting or {},
    )


def test_boldness_is_low_tradition_and_obedience_and_high_freedom() -> None:
    assert boldness(SUKI) == pytest.approx((0.9 + 0.95 + 0.9) / 3)
    assert boldness(MEI) == pytest.approx((0.7 + 0.8 + 0.5) / 3)
    assert boldness(VIKTOR) == pytest.approx((0.1 + 0.35 + 0.3) / 3)


def test_the_older_a_mural_the_readier_they_are_to_paint_over_it() -> None:
    assert ready(SUKI, 1) < ready(SUKI, 24) < ready(SUKI, 48) == ready(SUKI, 200)


def test_their_own_mural_is_fine_to_replace() -> None:
    assert ready(VIKTOR, 24, artist="viktor") > ready(MEI, 24) > ready(VIKTOR, 24)
    assert ready(VIKTOR, 24, artist="viktor") == ready(VIKTOR, 24, RIVAL, artist="viktor")


def test_bolder_painters_are_readier_to_paint_over_someone_elses() -> None:
    assert ready(SUKI, 24) > ready(MEI, 24) > ready(VIKTOR, 24)


def test_the_less_they_like_the_artist_the_readier_they_are() -> None:
    assert ready(MEI, 24, RIVAL) > ready(MEI, 24, STRANGER) > ready(MEI, 24, LIKED)


def test_only_the_boldest_ever_paint_over_a_friends_mural() -> None:
    assert readiness(MEI, mural("m", "x", hours_ago=500), FRIEND, NOW) is None
    assert readiness(SUKI, mural("m", "x", hours_ago=500), FRIEND, NOW) is not None


def test_a_blank_wall_comes_first_and_the_nearest_of_them(
    works: WorksStore, memory: MemoryStore
) -> None:
    near_other = {"suki": Point(23, 6)}

    assert walls(works, memory, near_other).pick(SUKI) == MuralSpot("wall_2", OTHER_WALL.stand)
    assert walls(works, memory).pick(SUKI) == MuralSpot("wall_1", WALL.stand)

    works.paint(mural("old", "viktor", "wall_1", hours_ago=500), "<svg/>", b"")
    assert walls(works, memory).pick(SUKI) == MuralSpot("wall_2", OTHER_WALL.stand)


def test_nobody_picks_a_wall_someone_else_is_painting(
    works: WorksStore, memory: MemoryStore
) -> None:
    others = {"mei": "wall_1", "viktor": "wall_2"}
    theirs = {"mei": "wall_1", "suki": "wall_2"}

    assert walls(works, memory, painting=others).pick(SUKI) is None
    assert walls(works, memory, painting=theirs).pick(SUKI) == MuralSpot("wall_2", OTHER_WALL.stand)


def test_picks_the_wall_they_are_readiest_to_paint_over(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.paint(mural("fresh", "viktor", "wall_1", hours_ago=1), "<svg/>", b"")
    works.paint(mural("faded", "viktor", "wall_2", hours_ago=12), "<svg/>", b"")

    assert walls(works, memory).pick(SUKI) == MuralSpot("wall_2", OTHER_WALL.stand)
    assert walls(works, memory).pick(VIKTOR) == MuralSpot("wall_2", OTHER_WALL.stand)
    assert walls(works, memory).pick(MEI) is None


def test_leaves_every_wall_alone_while_none_is_ready_enough(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.paint(mural("a", "mei", "wall_1", hours_ago=2), "<svg/>", b"")
    works.paint(mural("b", "mei", "wall_2", hours_ago=2), "<svg/>", b"")

    assert walls(works, memory).pick(VIKTOR) is None
    assert walls(works, memory).pick(SUKI) is None


def test_a_timid_painter_never_paints_over_a_friend(works: WorksStore, memory: MemoryStore) -> None:
    memory.add(feeling(MEI, "viktor", 0.9), feeling(SUKI, "viktor", 0.9))
    works.paint(mural("ancient", "viktor", "wall_1", hours_ago=1000), "<svg/>", b"")
    works.paint(mural("fresh", "suki", "wall_2", hours_ago=1), "<svg/>", b"")

    assert walls(works, memory).pick(MEI) is None
    assert walls(works, memory).pick(SUKI) == MuralSpot("wall_1", WALL.stand)

    later = walls(works, memory)
    later.clock.now = NOW + timedelta(days=10)
    assert later.pick(MEI) == MuralSpot("wall_2", OTHER_WALL.stand)


def test_the_murals_message_has_every_wall_and_what_is_on_it(
    works: WorksStore, memory: MemoryStore
) -> None:
    picker = walls(works, memory)
    assert [wall.mural for wall in picker.message().walls] == [None, None]

    works.paint(mural("first", "viktor"), "<svg/>", b"")
    works.paint(mural("second", "suki"), "<svg/>", b"")

    assert picker.message() == MuralsMessage(
        walls=[
            Wall(
                id="wall_1",
                x=10,
                y=5,
                width=3,
                face="south",
                bottom=0.5,
                top=1.5,
                mural=Mural(
                    work_id="second",
                    title="Piece second",
                    artist=Artist(id="suki", name=SUKI.name),
                    statement="What second says.",
                    image="/api/works/second.png",
                ),
            ),
            Wall(id="wall_2", x=20, y=5, width=2, face="east", bottom=0, top=1, mural=None),
        ]
    )
