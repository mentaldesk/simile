import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Behaviour
from simile.conversation import DEFAULT_CONFIG, ConversationConfig, ConversationEngine
from simile.conversation.player import PlayerConversations
from simile.debug import Village
from simile.debug.state import MAX_LINES, MAX_MEMORIES, MAX_RELATIONSHIPS, MAX_TEXT
from simile.llm import FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import PLAYER_ID, Flag, FlagKind, Memory, MemoryKind, Relationship
from simile.sim import Clock, FakeWallClock, LineSpoken, World
from simile.social import as_of, meet
from simile.world import Movement
from simile.world.map import load_map

pytestmark = pytest.mark.anyio

NPCS = {npc.id: npc for npc in load_npcs()}
START = datetime(2026, 1, 1, 10, tzinfo=UTC)


class Town:
    def __init__(
        self,
        records: Sequence[Relationship | Memory] = (),
        config: ConversationConfig = DEFAULT_CONFIG,
    ) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.memory = MemoryStore(":memory:")
        self.memory.add(*records)
        movement = Movement(load_map(), self.world.bus)
        movement.place(PLAYER_ID, "square")
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, movement, NPCS.values(), self.memory, seed=0
        )
        self.behaviour.start()
        llm = LLMClient(FakeProvider(default="Lovely morning for it. [values: connection]"))
        self.engine = ConversationEngine(
            self.world.clock,
            self.world.bus,
            self.behaviour,
            self.memory,
            lambda: llm,
            config=config,
            seed=0,
        )
        self.players = PlayerConversations(self.engine, seed=0)
        self.world.loop.register(movement)
        self.world.loop.register(self.engine)
        self.world.loop.register(self.players)
        self.village = Village(self.behaviour, self.engine, self.memory)

    def state(self, npc: str) -> dict:
        state = self.village.npc_state(npc)
        assert state is not None
        return state


def feeling(owner: str, about: str, **scores: object) -> Relationship:
    return meet(NPCS[owner], about).model_copy(update=scores)


def flag(id: str, kind: FlagKind, created: datetime, resolved: datetime | None = None) -> Flag:
    return Flag(
        id=id,
        kind=kind,
        owner="kofi",
        about="henrietta",
        description=f"{kind} {id}",
        created=created,
        resolved=resolved,
    )


def remembered(content: str, salience: float, hours_ago: float) -> Memory:
    return Memory(
        owner="kofi",
        kind=MemoryKind.OBSERVATION,
        content=content,
        salience=salience,
        valence=0.2,
        timestamp=START - timedelta(hours=hours_ago),
    )


def test_only_npcs_have_state() -> None:
    town = Town()

    assert town.village.npc_state("nobody") is None
    assert town.village.npc_state(PLAYER_ID) is None


def test_shows_who_they_are_what_they_want_and_their_top_values() -> None:
    town = Town()

    state = town.state("kofi")

    assert state["name"] == NPCS["kofi"].name
    assert state["occupation"] == NPCS["kofi"].occupation
    assert state["time"] == START.isoformat()
    assert state["goal"] == str(town.behaviour.goal("kofi"))
    assert set(state["needs"]) == {"social", "curiosity", "rest"}
    assert state["values"] == {
        "open_mindedness": 0.97,
        "adventure": 0.95,
        "creativity": 0.94,
        "freedom": 0.92,
        "equality": 0.91,
    }
    assert state["relationships"] == []
    assert state["memories"] == []
    assert state["conversation"] is None


def test_relationships_are_as_of_now_with_open_flags_first() -> None:
    earlier = START - timedelta(days=2)
    friend = feeling(
        "kofi",
        "henrietta",
        like=0.95,
        familiarity=0.8,
        last_interaction=earlier,
        flags=[
            flag("debt", FlagKind.DEBT, earlier, resolved=START),
            flag("grudge", FlagKind.GRUDGE, earlier - timedelta(days=1)),
        ],
    )
    player = feeling("kofi", PLAYER_ID, familiarity=0.1)
    town = Town([friend, player])

    rows = town.state("kofi")["relationships"]

    current = as_of(friend, START)
    assert current.like < 0.95
    assert rows[0] == {
        "about": "henrietta",
        "like": round(current.like, 3),
        "trust": round(current.trust, 3),
        "respect": round(current.respect, 3),
        "familiarity": round(current.familiarity, 3),
        "flags": [
            {"kind": "grudge", "description": "grudge grudge", "open": True},
            {"kind": "debt", "description": "debt debt", "open": False},
        ],
    }
    assert [row["about"] for row in rows] == ["henrietta", PLAYER_ID]


def test_memories_are_what_they_recall_now() -> None:
    town = Town(
        [remembered(f"Memory {n}", salience=0.5, hours_ago=n) for n in range(MAX_MEMORIES + 2)]
        + [remembered("x" * 1000, salience=1.0, hours_ago=1)]
    )

    memories = town.state("kofi")["memories"]

    expected = town.memory.recall("kofi", START, k=MAX_MEMORIES)
    assert [m["content"][:10] for m in memories] == [m.content[:10] for m in expected]
    assert memories[0]["content"] == "x" * (MAX_TEXT - 1) + "…"
    assert memories[1] == {
        "kind": "observation",
        "content": "Memory 0",
        "timestamp": START.isoformat(),
        "salience": 0.5,
        "valence": 0.2,
    }


async def test_shows_the_live_transcript_of_their_conversation() -> None:
    town = Town()
    conversation = town.engine.start("kofi", "henrietta")
    spoken: list[LineSpoken] = []
    town.world.bus.subscribe(LineSpoken, spoken.append)

    await town.world.loop.run(timedelta(seconds=6))

    state = town.state("henrietta")
    assert state["goal"] == "talk kofi"
    talk = state["conversation"]
    assert talk["id"] == conversation.id
    assert talk["talking_to"] == "kofi"
    assert {"engagement", "facing", "leaving"} <= set(talk)
    assert spoken
    assert talk["lines"] == [
        {
            "speaker": event.line.speaker,
            "text": event.line.text,
            "timestamp": event.line.timestamp.isoformat(),
        }
        for event in spoken[-MAX_LINES:]
    ]
    assert town.state("desmond")["conversation"] is None


async def test_shows_their_conversation_with_the_player() -> None:
    town = Town()
    town.behaviour.movement.place(PLAYER_ID, NPCS["kofi"].home)
    conversation = town.players.start("kofi", opener="kofi")

    await town.world.loop.run(timedelta(seconds=6))

    talk = town.state("kofi")["conversation"]
    assert talk["id"] == conversation.id
    assert talk["talking_to"] == PLAYER_ID
    assert talk["lines"]
    assert {line["speaker"] for line in talk["lines"]} == {"kofi"}


async def test_stays_small_however_much_they_know() -> None:
    known = [
        feeling("kofi", f"stranger_{n}", familiarity=n / 100, last_interaction=START)
        for n in range(MAX_RELATIONSHIPS + 5)
    ]
    long_memories = [remembered("y" * 5000, 0.9, hours_ago=n) for n in range(20)]
    town = Town([*known, *long_memories], ConversationConfig(min_lines=30, max_lines=40))
    town.engine.start("kofi", "henrietta")

    await town.world.loop.run(timedelta(minutes=1))

    state = town.state("kofi")
    assert len(state["relationships"]) == MAX_RELATIONSHIPS
    assert state["relationships"][0]["about"] == f"stranger_{MAX_RELATIONSHIPS + 4}"
    assert len(state["memories"]) == MAX_MEMORIES
    assert len(state["conversation"]["lines"]) == MAX_LINES
    assert len(json.dumps(state)) < 16_000
