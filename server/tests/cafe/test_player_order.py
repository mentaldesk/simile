from typing import Any

import pytest

from simile.cafe.events import Ordered, Served
from simile.cafe.orders import Order
from simile.conversation import ConversationEngine
from simile.conversation.player import PlayerConversations
from simile.schema import PLAYER_ID
from simile.sim import ConversationStarted, LineSpoken
from simile.world import Point

from .conftest import Village

pytestmark = pytest.mark.anyio

FLAT_WHITE = Order(says="One oat flat white, coming up.", drink="Oat flat white", menu="flat_white")


class Counter(Village):
    """The barista on shift, with B5 running the player's conversations and the player at the
    counter."""

    def __init__(self, replies: list[Any]) -> None:
        super().__init__(replies=replies)
        self.engine = ConversationEngine(
            self.world.clock, self.world.bus, self.behaviour, self.store, lambda: self.llm
        )
        self.players = PlayerConversations(self.engine, seed=0)
        self.engine.player_request = self.players.request
        self.players.writers["bea"] = self.cafe.write
        self.cafe.players = lambda: self.players
        self.world.loop.register(self.engine)
        self.world.loop.register(self.players)

    def said(self, speaker: str) -> list[str]:
        return [e.line.text for e in self.of(LineSpoken) if e.line.speaker == speaker]


async def at_the_counter(replies: list[Any]) -> Counter:
    counter = Counter(replies)
    await counter.run(seconds=15)
    counter.player_at_counter()
    await counter.run(seconds=2)
    return counter


async def test_the_barista_asks_what_the_player_would_like_without_the_llm() -> None:
    counter = await at_the_counter([])

    [started] = counter.of(ConversationStarted)
    assert started.conversation.participants == ["bea", PLAYER_ID]
    assert counter.said("bea") in (
        ["Hello! What can I get you?"],
        ["Hi there. What would you like?"],
    )
    assert counter.calls == []


async def test_the_player_orders_and_is_served_after_the_drinks_wait() -> None:
    counter = await at_the_counter([FLAT_WHITE])

    counter.players.say("A flat white with oat milk, please.", "bea")
    await counter.run(seconds=5)

    assert counter.said("bea")[-1] == "One oat flat white, coming up."
    [ordered] = counter.of(Ordered)
    assert (ordered.customer, ordered.drink, ordered.menu) == (
        PLAYER_ID,
        "oat flat white",
        "flat_white",
    )
    assert [call.purpose for call in counter.calls] == ["cafe-order"]
    assert counter.of(Served) == []

    await counter.run(seconds=60)
    [served] = counter.of(Served)
    assert (served.customer, served.drink) == (PLAYER_ID, "oat flat white")
    assert "oat flat white" in counter.said("bea")[-1]
    assert len(counter.of(ConversationStarted)) == 1


async def test_an_order_off_the_menu_is_improvised_and_takes_longer() -> None:
    matcha = Order(says="Matcha? I can do that.", drink="matcha latte", menu=None)
    counter = await at_the_counter([matcha])

    counter.players.say("Could I get a matcha latte?", "bea")
    await counter.run(seconds=80)

    [ordered] = counter.of(Ordered)
    assert (ordered.drink, ordered.menu) == ("matcha latte", None)
    assert counter.of(Served) == []
    await counter.run(seconds=15)
    assert [served.drink for served in counter.of(Served)] == ["matcha latte"]


async def test_a_menu_id_that_isnt_on_the_menu_counts_as_improvised() -> None:
    odd = Order(says="One cortado.", drink="cortado", menu="cortado")
    counter = await at_the_counter([odd])

    counter.players.say("A cortado, please.", "bea")
    await counter.run(seconds=5)

    [ordered] = counter.of(Ordered)
    assert ordered.menu is None


async def test_a_line_that_isnt_an_order_gets_an_answer_and_no_drink() -> None:
    browsing = Order(says="Take your time. The chai's good today.", drink=None, menu=None)
    counter = await at_the_counter([browsing])

    counter.players.say("Hmm, what's good?", "bea")
    await counter.run(seconds=5)

    assert counter.said("bea")[-1] == "The chai's good today."
    assert counter.of(Ordered) == []
    assert counter.cafe.player_job is None


async def test_a_drink_left_on_the_counter_is_called_out_without_a_conversation() -> None:
    counter = await at_the_counter([FLAT_WHITE])
    counter.players.say("A flat white with oat milk, please.", "bea")
    await counter.run(seconds=5)

    counter.movement.track(PLAYER_ID, Point(31, 15, "high_street"))
    await counter.run(seconds=60)

    assert counter.said("bea")[-1] == "Oat flat white for the Visitor!"
    assert len(counter.of(Served)) == 1
    assert len(counter.of(ConversationStarted)) == 1
