import asyncio
import itertools
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Behaviour
from simile.conversation import ConversationEngine
from simile.economy import OUTSIDE, Kind
from simile.economy.economy import Economy
from simile.llm import FakeProvider, LLMClient, Request
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.reflection import Extraction, Lending, NewFlag, Reflector
from simile.schema import CoreValue, Flag, FlagKind, MapTile, Npc
from simile.sim import Clock, ConversationEnded, FakeWallClock, World
from simile.social import lent, meet
from simile.world import Movement
from simile.world.map import load_maps

pytestmark = pytest.mark.anyio

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
TEMPLATE = load_npcs()[0]


def resident(id: str, home: str, money: float) -> Npc:
    """Someone with a savings target of 300 and no job."""
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": f"{id.title()} Test",
            "home": home,
            "values": dict.fromkeys(CoreValue, 0.5),
            "money": money,
            "workplace": None,
            "shifts": [],
            "pay": None,
        }
    )


def script(*lines: str) -> str:
    speakers = itertools.cycle(["Ana", "Ben"])
    return "".join(f"{next(speakers)}: {line} [values: connection]\n" for line in lines)


ASKS = script(
    "Ben, I'm short this week. Could you lend me a hundred to tide me over?",
    "Of course, Ana. Here's a hundred. Pay me back when you can.",
    "You're a lifesaver. Bye, Ben!",
    "Bye, Ana.",
)
TURNED_DOWN = script(
    "Ben, could you lend me a hundred to tide me over?",
    "Sorry, Ana, I don't lend money. Bye now.",
    "Fair enough. Bye, Ben.",
)
PAYS_BACK = script(
    "Here's the hundred you lent me, Ben. Thanks again.",
    "Cheers, Ana. Bye for now.",
    "Bye, Ben!",
)
CHAT = script("Lovely day, Ben.", "It is. Bye, Ana.", "Bye, Ben.")


def lends(amount: float, **extra: object) -> Extraction:
    """B3 finding that Ben lent Ana `amount`."""
    loans = [Lending(lender="ben", borrower="ana", amount=amount)]
    return Extraction.model_validate({"reflections": [], "loans": loans, **extra})


def resolves(*refs: str) -> Extraction:
    return Extraction(reflections=[], flags_resolved=list(refs))


class Village:
    """Ana, who's short, and her friend Ben at the café, with the economy, B2 and B3 on L1's
    fake provider."""

    def __init__(self, *, ana: float = 20, ben: float = 900, trust: float = 0.8) -> None:
        self.world = World(Clock(START), FakeWallClock())
        clock, bus = self.world.clock, self.world.bus
        self.store = MemoryStore(":memory:")
        npcs = [resident("ana", "house_1", ana), resident("ben", "house_2", ben)]
        self.store.add(
            meet(npcs[0], "ben").model_copy(update={"like": 0.9}),
            meet(npcs[1], "ana").model_copy(update={"like": 0.8, "trust": trust}),
        )
        movement = Movement(load_maps(), bus)
        for npc in npcs:
            movement.place(npc.id, MapTile(map="coffee_shop", x=13, y=8))
        behaviour = Behaviour(clock, bus, movement, npcs, self.store)
        behaviour.start()
        self.economy = Economy(clock, behaviour)
        behaviour.hooks.set(money=self.economy.money_of)
        self.provider = FakeProvider()
        self.llm = LLMClient(self.provider)
        self.engine = ConversationEngine(clock, bus, behaviour, self.store, lambda: self.llm)
        self.reflector = Reflector(
            self.store,
            lambda: behaviour.npcs,
            lambda: self.llm,
            settle=self.engine.settle,
            economy=lambda: self.economy,
        )
        bus.subscribe(ConversationEnded, self.reflector.on_ended)
        self.world.loop.register(movement)
        self.world.loop.register(self.engine)

    async def talk(self, lines: str, *reflection: object) -> tuple[str, str]:
        """A scene Ana starts with Ben from `lines`, once B3 has reflected on it: the prompts of
        the scene and the reflection."""
        await self.start(lines, *reflection)
        await asyncio.gather(*self.reflector.tasks)
        scene, reflecting = self.provider.requests[-2:]
        return scene.messages[-1].content, reflecting.messages[-1].content

    async def start(self, lines: str, *reflection: object) -> None:
        self.provider.replies.extend([lines, *reflection])
        self.engine.start("ana", "ben")
        await self.world.loop.run(timedelta(minutes=1))

    @property
    def money(self) -> dict[str, float]:
        return self.economy.money

    @property
    def flags(self) -> list[Flag]:
        return self.flags_of("ben", "ana")

    def flags_of(self, owner: str, about: str) -> list[Flag]:
        rel = self.store.relationship(owner, about)
        return rel.flags if rel else []

    def kinds(self) -> list[Kind]:
        return [entry.kind for entry in self.economy.ledger.entries]

    async def reflecting(self, count: int) -> None:
        """Until only `count` reflections are still under way."""
        while len(self.reflector.tasks) > count:
            await asyncio.sleep(0.01)

    def balanced(self) -> bool:
        return self.economy.ledger.gap(self.money) == 0


async def test_a_loan_agreed_in_conversation_moves_the_money_and_leaves_a_debt_flag() -> None:
    village = Village()

    scene, _ = await village.talk(ASKS, lends(100))

    assert (
        "- Ana is short of money and asks Ben to lend them 100 to tide them over. Ben trusts Ana "
        "and lends it." in scene
    )
    assert village.money == {"ana": 120, "ben": 800}
    [entry] = village.economy.ledger.entries
    assert (entry.kind, entry.payer, entry.payee, entry.amount) == (Kind.LOAN, "ben", "ana", 100)
    assert village.balanced()
    [flag] = village.flags
    assert (flag.kind, flag.description, flag.resolved) == (FlagKind.DEBT, "a loan of 100", None)
    assert lent(flag) == 100
    assert village.flags_of("ana", "ben") == []


async def test_repaying_it_resolves_the_flag() -> None:
    village = Village()
    await village.talk(ASKS, lends(100))
    village.economy.pay(OUTSIDE, "ana", 300, Kind.WAGE)

    scene, reflecting = await village.talk(PAYS_BACK, resolves("F1"))

    assert "- Ana has the money now, and pays back the 100 Ben lent them." in scene
    assert "F1 (debt): ana owes ben: a loan of 100" in reflecting
    assert village.money == {"ana": 320, "ben": 900}
    assert village.kinds() == [Kind.LOAN, Kind.WAGE, Kind.REPAYMENT]
    assert village.balanced()
    [flag] = village.flags
    assert flag.resolved is not None


async def test_a_friend_with_low_trust_declines() -> None:
    village = Village(trust=0.3)

    scene, _ = await village.talk(TURNED_DOWN, lends(100))

    assert "Ben doesn't trust Ana enough to lend money, and says no." in scene
    assert village.money == {"ana": 20, "ben": 900}
    assert village.kinds() == []
    assert village.flags == []


async def test_a_loan_is_capped_at_what_the_lender_agreed_to_and_can_spare() -> None:
    village = Village(ben=345)

    scene, _ = await village.talk(ASKS, lends(100))

    assert "Ben can only spare 40, and lends that." in scene
    assert village.money == {"ana": 60, "ben": 305}
    [flag] = village.flags
    assert lent(flag) == 40


@pytest.mark.parametrize("amount", [0, -20, 5000])
async def test_b3_cant_make_up_an_amount(amount: float) -> None:
    village = Village()

    await village.talk(ASKS, lends(amount))

    assert village.money == {"ana": 20, "ben": 900}
    assert village.flags == []


async def test_only_a_loan_the_scene_was_set_up_for_moves_money() -> None:
    village = Village(ana=200)

    scene, _ = await village.talk(CHAT, lends(100))

    assert "short of money" not in scene
    assert village.money == {"ana": 200, "ben": 900}
    assert village.flags == []


async def test_b3s_own_debt_flag_for_the_loan_isnt_kept_as_well() -> None:
    village = Village()
    debt = NewFlag(kind=FlagKind.DEBT, who="ana", whom="ben", description="the hundred Ben lent")

    await village.talk(ASKS, lends(100, flags_opened=[debt]))

    [flag] = village.flags
    assert flag.description == "a loan of 100"


async def test_a_loan_b3_calls_settled_without_paying_it_back_stays_open() -> None:
    village = Village()
    await village.talk(ASKS, lends(100))

    scene, _ = await village.talk(CHAT, resolves("F1"))

    assert "pays back" not in scene
    assert village.money == {"ana": 120, "ben": 800}
    [flag] = village.flags
    assert flag.resolved is None


async def test_a_repayment_the_borrower_can_no_longer_cover_leaves_the_loan_open() -> None:
    village = Village()
    await village.talk(ASKS, lends(100))
    village.economy.pay(OUTSIDE, "ana", 300, Kind.WAGE)

    def broke(request: Request) -> str:
        village.economy.pay("ana", OUTSIDE, 400, Kind.RENT)
        return resolves("F1").model_dump_json()

    await village.talk(PAYS_BACK, broke)

    assert village.money == {"ana": 20, "ben": 800}
    assert village.balanced()
    [flag] = village.flags
    assert flag.resolved is None


def held_back(release: asyncio.Event, reply: Extraction) -> Callable[[Request], Awaitable[str]]:
    """B3's `reply`, once `release` is set."""

    async def reflect(request: Request) -> str:
        await release.wait()
        return reply.model_dump_json()

    return reflect


async def test_a_second_scene_before_b3_has_reflected_on_an_ask_doesnt_lend_again() -> None:
    village = Village()
    release = asyncio.Event()

    await village.start(ASKS, held_back(release, lends(100)))
    await village.start(ASKS, lends(100))
    await asyncio.wait_for(village.reflecting(1), 1)

    second = village.provider.requests[2].messages[-1].content
    assert "short of money" not in second
    assert village.money == {"ana": 20, "ben": 900}
    release.set()
    await asyncio.gather(*village.reflector.tasks)
    assert village.money == {"ana": 120, "ben": 800}
    assert village.kinds() == [Kind.LOAN]
    [flag] = village.flags
    assert lent(flag) == 100


async def test_a_loan_is_paid_back_once() -> None:
    village = Village()
    await village.talk(ASKS, lends(100))
    village.economy.pay(OUTSIDE, "ana", 300, Kind.WAGE)
    release = asyncio.Event()

    await village.start(PAYS_BACK, held_back(release, resolves("F1")))
    await village.start(PAYS_BACK, resolves("F1"))
    await asyncio.wait_for(village.reflecting(1), 1)

    second = village.provider.requests[-2].messages[-1].content
    assert "pays back" not in second
    assert village.money == {"ana": 420, "ben": 800}
    release.set()
    await asyncio.gather(*village.reflector.tasks)
    assert village.money == {"ana": 320, "ben": 900}
    assert village.kinds() == [Kind.LOAN, Kind.WAGE, Kind.REPAYMENT]
