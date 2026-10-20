import asyncio
import itertools
import math
from datetime import UTC, datetime
from functools import partial

import pytest

from simile.conversation import LineDrafted
from simile.protocol import AudioChunk
from simile.schema import PLAYER_ID, Conversation, Id, Line, MapTile, Voice
from simile.sim import ConversationStarted, EventBus, LineSpoken
from simile.voice import FakeSynthesiser, VoiceService
from simile.voicing import DEFAULT_CONFIG
from simile.voicing.distance import apart, between
from simile.voicing.voicing import Voicing
from simile.world import Movement, Point
from simile.world.map import load_maps

STREETS = load_maps()
NOW = datetime(2026, 1, 1, 10, tzinfo=UTC)
VOICE = Voice(
    description="Warm.", reference_line="Hello.", reference_clip="content/voices/kofi.wav"
)
LANE = "lychee_lane"
LOOKOUT = 12
"""The row of the park's lookout, up a ladder above Lychee Lane's row 15."""


def test_measures_along_the_street_however_high_or_low_each_stands() -> None:
    lookout, lane = Point(48, LOOKOUT, LANE), Point(43, 15, LANE)
    promenade, row = Point(58, 18, "banyan_row"), Point(53, 15, "banyan_row")

    assert apart(lane, lookout) == apart(lookout, lane) == 5
    assert apart(row, promenade) == 5
    assert math.dist(lane, lookout) > DEFAULT_CONFIG.earshot


@pytest.mark.parametrize(
    ("here", "there"),
    [
        (Point(5, 2, "coffee_shop_floor_0"), Point(5, 2, "coffee_shop_floor_1")),
        (Point(30, 15, "high_street"), Point(5, 2, "coffee_shop_floor_0")),
        (Point(50, 15, "high_street"), Point(17, 15, LANE)),
    ],
    ids=["floor above", "inside from the street", "street through a door"],
)
def test_nobody_on_another_floor_or_map_is_in_reach(here: Point, there: Point) -> None:
    assert apart(here, there) == math.inf


def test_measures_as_movement_does_along_a_row() -> None:
    movement = Movement(STREETS, EventBus())
    movement.place("mei", MapTile(map="high_street", x=30, y=15))
    movement.place("viktor", MapTile(map="high_street", x=35, y=15))
    movement.track(PLAYER_ID, Point(5, 2, "coffee_shop_floor_0"))

    assert between(movement, "mei", "viktor") == movement.distance("mei", "viktor") == 5
    assert between(movement, "mei", PLAYER_ID) == movement.distance("mei", PLAYER_ID)
    with pytest.raises(KeyError):
        between(movement, "mei", "nobody")


class Street:
    """Voicing on the side-view maps, with I1's distances through `between`."""

    def __init__(self, voice: VoiceService) -> None:
        self.movement = Movement(STREETS, EventBus())
        self.sent: list[AudioChunk] = []
        self.voicing = Voicing(voice, partial(between, self.movement), self.sent.append)
        self._ids = itertools.count(1)

    def place(self, npc: Id, map: str, x: int, y: int) -> None:
        self.movement.place(npc, MapTile(map=map, x=x, y=y))

    def move_player(self, map: str, x: float, y: float) -> None:
        self.movement.track(PLAYER_ID, Point(x, y, map))
        self.voicing.tick(0.1)

    def start(self, *participants: Id) -> str:
        conversation = Conversation(
            id=f"talk-{next(self._ids)}", participants=list(participants), started=NOW
        )
        self.voicing.on_started(ConversationStarted(conversation))
        return conversation.id

    def say(self, conversation: str, speaker: Id, text: str) -> bool:
        line = Line(
            id=next(self._ids),
            conversation_id=conversation,
            speaker=speaker,
            text=text,
            timestamp=NOW,
            duration=1,
        )
        self.voicing.on_drafted(LineDrafted(line))
        voiced = self.voicing.voiced(line)
        self.voicing.on_spoken(LineSpoken(line))
        return voiced


type Place = tuple[str, float, float]

ON_THE_LOOKOUT: tuple[Place, Place] = ((LANE, 48, LOOKOUT), (LANE, 47, LOOKOUT))


def voiced_from(
    synthesiser: FakeSynthesiser, moves: list[Place], talking: tuple[Place, Place] = ON_THE_LOOKOUT
) -> list[bool]:
    """Mei and Viktor talk where they are while the player goes to each place in turn and hears a
    line there. Whether each line was voiced."""

    async def scenario() -> list[bool]:
        async with VoiceService(synthesiser) as voice:
            street = Street(voice)
            for npc, (map, x, y) in zip(("mei", "viktor"), talking, strict=True):
                await voice.add_voice(npc, VOICE)
                street.place(npc, map, int(x), int(y))
            street.move_player(*moves[0])
            talk = street.start("mei", "viktor")
            heard = []
            for n, move in enumerate(moves):
                street.move_player(*move)
                heard.append(street.say(talk, "mei" if n % 2 else "viktor", f"Line {n}."))
            await street.voicing.close()
            return heard

    return asyncio.run(scenario())


@pytest.mark.parametrize(("x", "voiced"), [(42, True), (41, False), (53, True), (54, False)])
def test_voices_a_conversation_within_earshot_along_the_street(
    synthesiser: FakeSynthesiser, x: float, voiced: bool
) -> None:
    assert voiced_from(synthesiser, [(LANE, x, 15)]) == [voiced]


def test_keeps_voicing_until_the_player_is_out_of_earshot_along_the_street(
    synthesiser: FakeSynthesiser,
) -> None:
    out = 47 - DEFAULT_CONFIG.out_of_earshot
    moves = [(LANE, 42, 15), (LANE, out, 15), (LANE, out - 0.1, 15), (LANE, out, 15)]

    assert voiced_from(synthesiser, moves) == [True, True, False, False]


def test_voices_nothing_on_another_street(synthesiser: FakeSynthesiser) -> None:
    assert voiced_from(synthesiser, [("high_street", 47, 15), (LANE, 45, 15)]) == [False, True]


def test_voices_nothing_upstairs_to_the_player_downstairs_or_outside(
    synthesiser: FakeSynthesiser,
) -> None:
    upstairs: tuple[Place, Place] = (("coffee_shop_floor_1", 5, 2), ("coffee_shop_floor_1", 6, 2))
    moves = [("coffee_shop_floor_0", 5, 2), ("high_street", 30, 15), ("coffee_shop_floor_1", 5, 2)]

    assert voiced_from(synthesiser, moves, upstairs) == [False, False, True]
