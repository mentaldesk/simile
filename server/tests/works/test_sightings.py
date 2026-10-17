import asyncio
from datetime import timedelta

import pytest

from simile.llm import FakeProvider, LLMClient, LLMError, Model
from simile.memory import MemoryStore
from simile.news.reactions import system_prompt
from simile.schema import PLAYER_ID, Memory, MemoryKind
from simile.sim import Clock
from simile.works import DEFAULT_CONFIG, WorksStore
from simile.works.reading import Reaction
from simile.works.sightings import Passers, distance_in_front
from simile.world.movement import Point

from .conftest import MEI, NOW, OTHER_WALL, SUKI, VIKTOR, WALL, mural

NPCS = {npc.id: npc for npc in (VIKTOR, SUKI, MEI)}
REACTION = Reaction(take="Cheerful, I'll give it that.", valence=0.3, intensity=0.4)
IN_FRONT, FAR, BEHIND = Point(11, 7), Point(11, 12), Point(11, 4)


def passers(
    works: WorksStore,
    memory: MemoryStore,
    positions: dict[str, Point],
    llm: LLMClient | None = None,
) -> Passers:
    return Passers(
        works, memory, Clock(NOW), lambda: llm, NPCS, [WALL, OTHER_WALL], lambda: positions
    )


async def walk_by(passers: Passers, seconds: int = 5) -> None:
    for _ in range(seconds * 10):
        passers.tick(0.1)
        await asyncio.sleep(0)
    await asyncio.gather(*passers.tasks)


def work_memories(memory: MemoryStore, owner: str) -> list[Memory]:
    return memory.recall(owner, NOW, kind=MemoryKind.WORK)


@pytest.mark.parametrize(
    ("position", "distance"),
    [
        (IN_FRONT, 1.5),
        (Point(10, 6), 0.5),
        (Point(15, 7), (1.5**2 + 2.5**2) ** 0.5),
        (FAR, 6.5),
        (BEHIND, None),
        (Point(11, 5), None),
    ],
)
def test_how_far_someone_is_in_front_of_a_south_face(
    position: Point, distance: float | None
) -> None:
    assert distance_in_front(WALL, position) == pytest.approx(distance)


def test_how_far_someone_is_in_front_of_an_east_face() -> None:
    assert distance_in_front(OTHER_WALL, Point(22, 6)) == pytest.approx(1.5)
    assert distance_in_front(OTHER_WALL, Point(20, 6)) is None


def test_a_passer_by_reacts_to_a_mural_once(works: WorksStore, memory: MemoryStore) -> None:
    works.paint(mural("m1", "suki"), "<svg/>", b"")
    fake = FakeProvider([REACTION])
    positions = {"viktor": IN_FRONT, "mei": FAR, "suki": IN_FRONT, "nobody": IN_FRONT}

    asyncio.run(walk_by(passers(works, memory, positions, LLMClient(fake))))

    [request] = fake.requests
    assert request.model == Model.HAIKU_5_5
    assert request.system.startswith(system_prompt(VIKTOR))
    asked = request.messages[-1].content
    assert asked.startswith(
        "You've just walked past a mural on the wall 1 wall, by Suki Tan, who paints bright "
        'murals.\n\nIt\'s called "Piece m1". A line.\n\nSuki Tan says of it: What m1 says.\n\n'
    )
    assert "painted over" not in asked
    assert work_memories(memory, "viktor") == [
        Memory(
            owner="viktor",
            kind=MemoryKind.WORK,
            content='I saw Suki Tan\'s mural "Piece m1" on the wall 1 wall. '
            "Cheerful, I'll give it that.",
            salience=0.4,
            valence=0.3,
            timestamp=NOW,
            about=["suki"],
            topics=[],
            work_id="m1",
        )
    ]
    assert work_memories(memory, "mei") == work_memories(memory, "suki") == []


def test_the_player_remembers_a_mural_without_a_call(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.paint(mural("m1", "suki"), "<svg/>", b"")
    fake = FakeProvider([])

    asyncio.run(walk_by(passers(works, memory, {PLAYER_ID: IN_FRONT}, LLMClient(fake))))

    assert fake.requests == []
    [seen] = work_memories(memory, PLAYER_ID)
    assert seen.content == 'I saw Suki Tan\'s mural "Piece m1" on the wall 1 wall.'
    assert (seen.salience, seen.valence, seen.about, seen.work_id) == (
        DEFAULT_CONFIG.player_salience,
        0,
        ["suki"],
        "m1",
    )


def test_an_artist_remembers_being_painted_over_when_they_next_see_the_wall(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.paint(mural("mine", "viktor"), "<svg/>", b"")
    works.paint(mural("over", "suki"), "<svg/>", b"")
    fake = FakeProvider([REACTION, REACTION])
    positions = {"viktor": IN_FRONT}

    asyncio.run(walk_by(passers(works, memory, positions, LLMClient(fake))))
    positions["mei"] = IN_FRONT
    asyncio.run(walk_by(passers(works, memory, positions, LLMClient(fake))))

    his, hers = (request.messages[-1].content for request in fake.requests)
    assert 'It\'s painted over your own mural there, "Piece mine".' in his
    assert "painted over" not in hers
    [memory_of_it] = work_memories(memory, "viktor")
    assert memory_of_it.content == (
        'Suki Tan has painted "Piece over" over my mural "Piece mine" on the wall 1 wall. '
        "Cheerful, I'll give it that."
    )
    assert memory_of_it.salience == DEFAULT_CONFIG.painted_over_salience
    assert memory_of_it.work_id == "over"


def test_a_look_that_fails_is_had_again_an_hour_later_and_not_before(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.paint(mural("m1", "suki"), "<svg/>", b"")
    fake = FakeProvider(default=lambda _: [LLMError("usage limit reached")])
    watcher = passers(works, memory, {"viktor": IN_FRONT, "mei": IN_FRONT}, LLMClient(fake))

    asyncio.run(walk_by(watcher, seconds=60))
    failed = len(fake.requests)
    watcher.clock.now = NOW + DEFAULT_CONFIG.look_again - timedelta(seconds=1)
    asyncio.run(walk_by(watcher, seconds=1))
    too_soon = len(fake.requests)
    watcher.clock.now = NOW + DEFAULT_CONFIG.look_again
    fake.default = REACTION.model_dump_json()
    asyncio.run(walk_by(watcher, seconds=60))

    assert (failed, too_soon, len(fake.requests)) == (2, 2, 4)
    assert [m.work_id for m in work_memories(memory, "viktor")] == ["m1"]
    assert [m.work_id for m in work_memories(memory, "mei")] == ["m1"]


def test_nobody_sees_a_mural_without_an_llm_or_twice_across_restarts(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.paint(mural("m1", "suki"), "<svg/>", b"")
    fake = FakeProvider([REACTION])

    asyncio.run(walk_by(passers(works, memory, {"viktor": IN_FRONT})))
    asyncio.run(walk_by(passers(works, memory, {"viktor": IN_FRONT}, LLMClient(fake))))
    asyncio.run(walk_by(passers(works, memory, {"viktor": IN_FRONT}, LLMClient(fake))))

    assert len(fake.requests) == 1
    assert len(work_memories(memory, "viktor")) == 1
