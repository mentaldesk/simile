import itertools
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Behaviour
from simile.conversation import DEFAULT_CONFIG, ConversationConfig, ConversationEngine
from simile.conversation.loans import Ask, Loan, Purse, Repayment, arrange, told
from simile.conversation.plan import Stance, direction, plan
from simile.llm import FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import CoreValue, MapTile, Npc, Relationship
from simile.sim import Clock, FakeWallClock, World
from simile.social import loan, meet, open_flag
from simile.world import Movement
from simile.world.map import load_maps

pytestmark = pytest.mark.anyio

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
TARGET = 300.0
NAMES = {"ana": "Ana", "ben": "Ben"}


def resident(id: str, home: str) -> Npc:
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": f"{id.title()} Test",
            "home": home,
            "values": dict.fromkeys(CoreValue, 0.5),
            "workplace": None,
            "shifts": [],
            "pay": None,
        }
    )


ANA, BEN = resident("ana", "house_1"), resident("ben", "house_2")


def feeling(owner: Npc, about: str, *, like: float = 0.8, trust: float = 0.8) -> Relationship:
    return meet(owner, about).model_copy(update={"like": like, "trust": trust})


def feelings(
    ana_likes: float = 0.8, ben_trusts: float = 0.8, ben_likes: float = 0.8
) -> dict[str, Relationship]:
    return {
        "ana": feeling(ANA, "ben", like=ana_likes),
        "ben": feeling(BEN, "ana", like=ben_likes, trust=ben_trusts),
    }


def purses(ana: float, ben: float) -> dict[str, Purse]:
    return {"ana": Purse(ana, TARGET), "ben": Purse(ben, TARGET)}


def test_a_resident_short_of_money_asks_a_friend_who_trusts_them() -> None:
    assert arrange(purses(40, 900), feelings()) == Ask("ana", "ben", 100, 100, True)
    assert arrange(purses(900, 40), feelings(ben_likes=0.8)) == Ask("ben", "ana", 100, 100, True)


def test_they_ask_for_what_takes_them_back_to_their_target_in_tens() -> None:
    config = ConversationConfig(max_loan=500)

    assert arrange(purses(113, 900), feelings(), config) == Ask("ana", "ben", 190, 190, True)


def test_a_lender_lends_what_they_have_above_their_own_target_in_tens() -> None:
    assert arrange(purses(40, 345), feelings()) == Ask("ana", "ben", 100, 40, True)
    assert arrange(purses(40, 305), feelings()) == Ask("ana", "ben", 100, 0, True)


def test_a_friend_with_low_trust_says_no() -> None:
    low = DEFAULT_CONFIG.lend_trust - 0.01

    assert arrange(purses(40, 900), feelings(ben_trusts=low)) == Ask("ana", "ben", 100, 0, False)


@pytest.mark.parametrize(
    ("money", "rels", "declined"),
    [
        pytest.param(purses(200, 900), feelings(), (), id="not short"),
        pytest.param(purses(40, 900), feelings(ana_likes=0.5), (), id="not a friend"),
        pytest.param(purses(40, 900), feelings(), [("ana", "ben")], id="turned down lately"),
    ],
)
def test_no_ask(
    money: Mapping[str, Purse], rels: Mapping[str, Relationship], declined: list[tuple[str, str]]
) -> None:
    assert arrange(money, rels, declined=declined) is None


def owing(amount: int = 100) -> dict[str, Relationship]:
    rels = feelings()
    rels["ben"] = open_flag(rels["ben"], loan("ben", "ana", amount, "talk_1", START))
    return rels


def test_a_borrower_pays_a_loan_back_once_that_leaves_them_short_of_nothing() -> None:
    rels = owing()

    paid = arrange(purses(300, 900), rels)

    assert paid == Repayment("ana", "ben", rels["ben"].flags[0])
    assert isinstance(paid, Repayment) and paid.amount == 100


def test_a_borrower_still_short_neither_pays_back_nor_asks_again() -> None:
    assert arrange(purses(150, 900), owing()) is None


def test_nothing_is_settled_between_two_with_a_loan_pending() -> None:
    rels = owing()
    asked = Ask("ana", "ben", 100, 100, True)
    paying = Repayment("ana", "ben", rels["ben"].flags[0])

    assert arrange(purses(40, 900), feelings(), pending=[asked]) is None
    assert arrange(purses(40, 900), feelings(), pending=[Ask("ben", "ana", 100, 0, False)]) is None
    assert arrange(purses(300, 900), rels, pending=[paying]) is None


def test_nobody_asks_while_an_ask_of_theirs_is_pending() -> None:
    elsewhere = Ask("ana", "cal", 100, 100, True)
    someone_else = Ask("cal", "ben", 100, 100, True)

    assert arrange(purses(40, 900), feelings(), pending=[elsewhere]) is None
    assert arrange(purses(40, 900), feelings(), pending=[someone_else]) == Ask(
        "ana", "ben", 100, 100, True
    )


def test_the_direction_tells_the_scene_what_happens() -> None:
    asks = "Ana is short of money and asks Ben to lend them 100 to tide them over."

    assert told(Ask("ana", "ben", 100, 100, True), NAMES) == f"{asks} Ben trusts Ana and lends it."
    assert told(Ask("ana", "ben", 100, 40, True), NAMES) == (
        f"{asks} Ben can only spare 40, and lends that."
    )
    assert (
        told(Ask("ana", "ben", 100, 0, True), NAMES) == f"{asks} Ben can't spare it, and says no."
    )
    assert told(Ask("ana", "ben", 100, 0, False), NAMES) == (
        f"{asks} Ben doesn't trust Ana enough to lend money, and says no."
    )
    flag = owing()["ben"].flags[0]
    assert told(Repayment("ana", "ben", flag), NAMES) == (
        "Ana has the money now, and pays back the 100 Ben lent them."
    )


def test_the_loan_goes_in_the_direction_before_the_ending() -> None:
    stances = {"ana": Stance(0.6, 6), "ben": Stance(0.6, 6)}

    lines = direction(plan(NAMES, stances, "ana", loan=Ask("ana", "ben", 100, 0, False)))

    assert lines.splitlines()[-2:] == [
        "- Ana is short of money and asks Ben to lend them 100 to tide them over. Ben doesn't "
        "trust Ana enough to lend money, and says no.",
        "- Ana speaks first. About 8 lines in all, ending when Ben takes their leave and Ana "
        "answers.",
    ]


CHAT = "Ana: Morning, Ben! [values: connection]\nBen: Bye then. [values: connection]\n"


class Village:
    """Ana and Ben at the café, with what they hold from `money` and a scene engine."""

    def __init__(
        self,
        money: dict[str, float] | None,
        rels: Mapping[str, Relationship],
        config: ConversationConfig = DEFAULT_CONFIG,
    ) -> None:
        self.world = World(Clock(START), FakeWallClock())
        store = MemoryStore(":memory:")
        store.add(*rels.values())
        movement = Movement(load_maps(), self.world.bus)
        for npc in (ANA, BEN):
            movement.place(npc.id, MapTile(map="coffee_shop_floor_0", x=12, y=2))
        behaviour = Behaviour(self.world.clock, self.world.bus, movement, [ANA, BEN], store)
        behaviour.start()
        if money is not None:
            behaviour.hooks.set(money=lambda npc: money[npc.id])
        self.provider = FakeProvider(itertools.repeat(CHAT, 10))
        llm = LLMClient(self.provider)
        self.engine = ConversationEngine(
            self.world.clock, self.world.bus, behaviour, store, lambda: llm, config=config
        )
        self.world.loop.register(movement)
        self.world.loop.register(self.engine)
        self.scenes: list[str] = []

    async def scene(self) -> str:
        """The prompt of a scene Ana starts with Ben, once it's over."""
        conversation = self.engine.start("ana", "ben")
        self.scenes.append(conversation.id)
        await self.world.loop.run(timedelta(minutes=1))
        ended = self.engine.conversation(conversation.id)
        assert ended is not None and ended.ended is not None
        return self.provider.requests[-1].messages[-1].content

    def settle(self, scene: int = -1) -> Loan | None:
        """What B3 gets for a scene, the latest unless told."""
        return self.engine.settle(self.scenes[scene])


async def test_a_scene_between_a_short_resident_and_a_friend_has_the_ask() -> None:
    village = Village({"ana": 40, "ben": 900}, feelings())

    prompt = await village.scene()

    assert "- Ana is short of money and asks Ben to lend them 100" in prompt
    assert village.settle() == Ask("ana", "ben", 100, 100, True)
    assert village.settle() is None


async def test_someone_turned_down_doesnt_ask_again_for_a_while() -> None:
    config = ConversationConfig(ask_again=timedelta(minutes=1.5))
    village = Village({"ana": 40, "ben": 900}, feelings(ben_trusts=0.3), config)

    prompts = []
    for _ in range(3):
        prompts.append(await village.scene())
        village.settle()
    first, second, third = prompts

    assert "says no" in first
    assert "short of money" not in second
    assert "says no" in third


async def test_an_ask_b3_hasnt_settled_yet_isnt_asked_again() -> None:
    village = Village({"ana": 40, "ben": 900}, feelings())

    first, second = await village.scene(), await village.scene()

    assert "asks Ben to lend them 100" in first
    assert "short of money" not in second
    assert village.settle(1) is None
    assert village.settle(0) == Ask("ana", "ben", 100, 100, True)
    assert "asks Ben to lend them 100" in await village.scene()


async def test_without_an_economy_nobody_asks() -> None:
    village = Village(None, feelings())

    prompt = await village.scene()

    assert "short of money" not in prompt
    assert village.settle() is None
