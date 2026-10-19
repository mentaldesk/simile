import asyncio
from datetime import timedelta

import pytest

from simile.llm import FakeProvider, LLMClient, LLMError
from simile.llm.client import CallRecord
from simile.memory import MemoryStore
from simile.protocol import Artist
from simile.protocol import Notice as Posted
from simile.schema import Id, Medium, Shift, Weekday
from simile.sim import Clock
from simile.works import DEFAULT_CONFIG, Maker, WorksStore
from simile.works.lifespan import shopkeepers
from simile.works.notices import Draft, Noticeboard
from simile.works.player import PlayerWorks
from simile.works.store import Notice

from .conftest import MEI, NOW, SUKI, VIKTOR, reply

BARISTA = MEI.model_copy(
    update={
        "workplace": "coffee_shop",
        "shifts": [Shift(days=[Weekday.SATURDAY, Weekday.SUNDAY], start=7, end=15.5)],
    }
)
NPCS = {npc.id: npc for npc in (VIKTOR, SUKI, BARISTA)}


def draft(title: str = "Two-for-one flat whites", text: str = "All afternoon.") -> str:
    return Draft(title=title, text=text).model_dump_json()


def board(
    works: WorksStore,
    clock: Clock,
    llm: LLMClient | None,
    asleep: set[Id] | None = None,
) -> Noticeboard:
    return Noticeboard(
        works,
        clock,
        lambda: llm,
        NPCS,
        ["mei", "nobody"],
        awake=lambda npc: npc not in (asleep or set()),
    )


async def post_due(noticeboard: Noticeboard) -> list[Notice | None]:
    tasks = [noticeboard.post(poster) for poster in noticeboard.due()]
    return await asyncio.gather(*(task for task in tasks if task is not None))


def test_a_shopkeeper_puts_up_a_notice_on_haiku_apart_from_the_works(works: WorksStore) -> None:
    fake = FakeProvider([draft()])
    calls: list[CallRecord] = []
    noticeboard = board(works, Clock(NOW), LLMClient(fake, listeners=[calls.append]))

    [notice] = asyncio.run(post_due(noticeboard))

    assert notice is not None
    assert (notice.poster, notice.title, notice.text, notice.created) == (
        "mei",
        "Two-for-one flat whites",
        "All afternoon.",
        NOW,
    )
    assert works.empty()
    assert works.by("mei") == []
    [request] = fake.requests
    assert request.model == DEFAULT_CONFIG.notice_model
    assert [call.purpose for call in calls] == ["notice"]
    asked = request.messages[-1].content
    assert asked.startswith("It's Saturday, 12:00. You work at the coffee shop: Saturday, Sunday")
    assert "07:00 to 15:30" in asked
    assert "an offer, an event or an invitation" in asked


def test_notices_are_not_works_so_nobody_reads_or_riffs_on_them(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.post(Notice(id="n1", poster="mei", title="Quiz night", text="Friday.", created=NOW))
    fake = FakeProvider([reply()])
    llm = LLMClient(fake)

    async def write() -> None:
        task = Maker(works, memory, Clock(NOW), lambda: llm, npcs=NPCS).make(VIKTOR)
        assert task is not None
        await task

    asyncio.run(write())

    assert "Quiz night" not in fake.requests[0].messages[-1].content
    assert [work.medium for work in works.by("viktor")] == [Medium.WRITING]
    noticeboard = board(works, Clock(NOW), None)
    listing = PlayerWorks(works, memory, Clock(NOW), NPCS, notices=noticeboard.board).listing()
    assert [work.artist.id for work in listing.works] == ["viktor"]
    assert listing.notices == [
        Posted(
            notice_id="n1",
            title="Quiz night",
            text="Friday.",
            poster=Artist(id="mei", name="Mei Lin"),
            created=NOW,
        )
    ]


def test_one_notice_every_so_often_on_days_they_work_while_awake(works: WorksStore) -> None:
    clock = Clock(NOW)
    fake = FakeProvider([draft("First"), draft("Second")])
    llm = LLMClient(fake)

    assert board(works, clock, llm, asleep={"mei"}).due() == []
    assert board(works, Clock(NOW - timedelta(days=2)), llm).due() == []
    noticeboard = board(works, clock, llm)
    asyncio.run(post_due(noticeboard))
    clock.now = NOW + DEFAULT_CONFIG.notice_every - timedelta(minutes=1)
    assert noticeboard.due() == []
    clock.now = NOW + DEFAULT_CONFIG.notice_every
    [second] = asyncio.run(post_due(noticeboard))

    assert second is not None and second.title == "Second"
    assert 'Your last notice was "First": All afternoon. Put up something else.' in (
        fake.requests[1].messages[-1].content
    )


def test_a_failed_notice_waits_before_trying_again(works: WorksStore) -> None:
    clock = Clock(NOW)
    noticeboard = board(works, clock, LLMClient(FakeProvider([LLMError("limit")])))

    assert asyncio.run(post_due(noticeboard)) == [None]
    assert noticeboard.due() == []
    clock.now = NOW + DEFAULT_CONFIG.look_again
    assert noticeboard.due() == ["mei"]


def test_the_board_shows_the_newest_notices_still_up(works: WorksStore) -> None:
    for n in range(4):
        created = NOW - timedelta(hours=n * 10)
        works.post(Notice(id=f"n{n}", poster="mei", title=f"N{n}", text="x", created=created))
    config = DEFAULT_CONFIG.model_copy(update={"notices_listed": 2})
    noticeboard = Noticeboard(
        works, Clock(NOW), lambda: None, NPCS, ["mei"], awake=lambda _: True, config=config
    )

    assert [notice.notice_id for notice in noticeboard.board()] == ["n0", "n1"]
    noticeboard.config = DEFAULT_CONFIG
    assert [notice.notice_id for notice in noticeboard.board()] == ["n0", "n1", "n2"]


def test_todays_shopkeepers_put_up_notices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("simile.casting.load_cast", lambda: None)

    assert shopkeepers() == ["priya", "odalys", "mirela"]
