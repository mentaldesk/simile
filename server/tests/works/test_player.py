from collections.abc import Callable

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.memory import MemoryStore, memory_of
from simile.protocol import Artist, WrittenWork
from simile.schema import PLAYER_ID, Medium, Memory, MemoryKind
from simile.sim import Clock
from simile.works import WorksStore, works_of
from simile.works.config import WorksConfig
from simile.works.player import PlayerWorks

from .conftest import MEI, NOW, SUKI, VIKTOR, work

MakePackage = Callable[[dict[str, str]], str]
NPCS = {npc.id: npc for npc in (VIKTOR, SUKI, MEI)}


@pytest.fixture
def player(works: WorksStore, memory: MemoryStore) -> PlayerWorks:
    for n in range(3):
        works.add(work(f"w{n}", hours_ago=n))
    return PlayerWorks(works, memory, Clock(NOW), NPCS)


def player_works(memory: MemoryStore) -> list[Memory]:
    return memory.recall(PLAYER_ID, NOW, kind=MemoryKind.WORK, k=100)


def test_lists_the_newest_writing_unread(works: WorksStore, memory: MemoryStore) -> None:
    works.add(work("old", hours_ago=3))
    works.add(work("poem", artist="viktor", hours_ago=1, text="One.\n\nTwo."))
    works.add(work("mural", artist="suki", medium=Medium.MURAL))
    works.add(work("stranger", artist="desmond", hours_ago=2))
    player = PlayerWorks(works, memory, Clock(NOW), NPCS, config=WorksConfig(listed=2))

    assert player.listing().works == [
        WrittenWork(
            work_id="poem",
            title="Piece poem",
            artist=Artist(id="viktor", name="Viktor Hale"),
            form="plain verse about old bridges",
            text="One.\n\nTwo.",
            statement="What poem says.",
            created=NOW.replace(hour=11),
            read=False,
        ),
        WrittenWork(
            work_id="stranger",
            title="Piece stranger",
            artist=Artist(id="desmond", name="Desmond"),
            form="plain verse about old bridges",
            text="A line.",
            statement="What stranger says.",
            created=NOW.replace(hour=10),
            read=False,
        ),
    ]


def test_reading_a_work_stores_the_players_memory_of_it(
    player: PlayerWorks, memory: MemoryStore, works: WorksStore
) -> None:
    works.add(work("w1", hours_ago=1, tags=["bridges", "repair", "rust", "the council"]))

    reply = player.read("w1")

    assert [w.read for w in reply.works] == [False, True, False]
    assert player_works(memory) == [
        Memory(
            owner=PLAYER_ID,
            kind=MemoryKind.WORK,
            content='I read Viktor Hale\'s "Piece w1" on the news terminal.',
            salience=0.5,
            valence=0,
            timestamp=NOW,
            about=["viktor"],
            topics=["bridges", "repair", "rust"],
            work_id="w1",
        )
    ]
    assert player.listing() == reply


def test_reading_a_work_again_stores_nothing_more(player: PlayerWorks, memory: MemoryStore) -> None:
    player.read("w2")
    player.read("w2")

    assert [m.work_id for m in player_works(memory)] == ["w2"]


@pytest.mark.parametrize("work_id", ["nope", "mural"])
def test_only_writing_is_read(
    player: PlayerWorks, memory: MemoryStore, works: WorksStore, work_id: str
) -> None:
    works.add(work("mural", artist="suki", medium=Medium.MURAL))

    reply = player.read(work_id)

    assert player_works(memory) == []
    assert [w.work_id for w in reply.works] == ["w0", "w1", "w2"]


def test_the_terminal_lists_and_reads_works_over_the_websocket(
    make_package: MakePackage,
) -> None:
    package = make_package(
        {
            "memory/lifespan.py": "from simile.memory.lifespan import lifespan\n",
            "works/lifespan.py": "from simile.works.lifespan import lifespan\n",
            "protocol/routes.py": "from simile.protocol.routes import routes\n",
            "sim/lifespan.py": "from simile.sim.lifespan import running\n",
        }
    )
    app = create_app(package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        works_of(app).add(work("w0", artist="tobias"))
        works_of(app).add(work("w1", artist="tobias", hours_ago=1))
        assert ws.receive_json()["type"] == "snapshot"

        ws.send_json({"type": "list_works"})
        listed = ws.receive_json()
        ws.send_json({"type": "read_work", "work_id": "w1"})
        read = ws.receive_json()
        ws.send_json({"type": "read_work", "work_id": "w1"})
        again = ws.receive_json()

        memories = memory_of(app).recall(PLAYER_ID, NOW, kind=MemoryKind.WORK)

    assert listed["type"] == read["type"] == "works"
    assert [(w["work_id"], w["artist"], w["read"]) for w in listed["works"]] == [
        ("w0", {"id": "tobias", "name": "Tobias Fallon"}, False),
        ("w1", {"id": "tobias", "name": "Tobias Fallon"}, False),
    ]
    assert [(w["work_id"], w["read"]) for w in read["works"]] == [("w0", False), ("w1", True)]
    assert again == read
    assert [m.work_id for m in memories] == ["w1"]
