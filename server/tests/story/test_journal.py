from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.llm import FakeProvider
from simile.persistence import investigation_of, player_of
from simile.protocol import PickUpMessage, hub_of
from simile.schema import (
    PLAYER_ID,
    Bionic,
    Body,
    Fact,
    HowKnown,
    Incident,
    Investigation,
    Item,
    ItemKind,
    JournalEntry,
    Knower,
    Lead,
    MapTile,
    Pile,
    Player,
    Source,
    SourceKind,
)
from simile.sim import Clock, LineSpoken, World
from simile.story import NOTES, load_story, says
from simile.story.journal import Journal
from simile.story.recording import Recorder
from simile.world import Point, movement_of

from ..conversation.test_bionics import watched
from ..conversation.test_player import START, make_npc
from ..conversation.test_telling import LONG_AGO, investigating
from .test_begin import run_village

NIGHT = START - timedelta(days=8)
ALIBI = "I was at home all night."
DEFLECTION = "No idea, I'm afraid."
ASLEEP = "I was fast asleep that night. I didn't hear a thing."
EYE = Player(body=Body(left_eye=Bionic.INFRARED_EYE))


def fact(
    id: str, *known_by: Knower, found_in: str | None = None, leads: tuple[str, ...] = ()
) -> Fact:
    return Fact(
        id=id,
        what=f"What happened: {id}.",
        when=NIGHT,
        where="maker_space",
        about=["aris", "ben"],
        known_by=list(known_by),
        found_in=found_in,
        leads=[Lead(fact_id=to, text=f"Follow {to}.") for to in leads],
    )


def saw(id: str, tells_from: float, cover: str | None = None) -> Knower:
    return Knower(id=id, how=HowKnown.WITNESSED, tells_from=tells_from, cover=cover)


def did(cover: str) -> Knower:
    return Knower(id="ben", how=HowKnown.DID, tells_from=None, cover=cover)


GONE = fact("gone", saw("ana", 0.0), saw("ben", 0.0), leads=("notes", "seen"))
FOUND = fact("notes", found_in=NOTES, leads=("there_ben", "seen"))
SEEN = fact("seen", saw("ana", 0.3), leads=("there_ben",))
SHOUTING = fact("shouting", saw("ana", 0.9, ASLEEP))
MEETING = fact("meeting", saw("ana", 0.9))
ATTACK = fact("attack", did(DEFLECTION))
THERE = fact("there_ben", did(ALIBI))
INCIDENT = Incident(
    attackers=["ben"],
    motive="Ben blamed Aris for a deal that fell through.",
    night=NIGHT,
    facts=[GONE, FOUND, SEEN, SHOUTING, MEETING, ATTACK, THERE],
)
ANA, BEN = GONE.known_by


class Notebook:
    """A journal of `INCIDENT` on a clock moved by hand, for a player who may have the eye."""

    def __init__(self, player: Player | None = None) -> None:
        self.investigation = Investigation(incident=INCIDENT.model_copy(deep=True))
        self.clock = Clock(START)
        self.player = player or Player()
        self.journal = Journal(self.investigation, lambda: self.clock.now, lambda: self.player)

    @property
    def entries(self) -> list[JournalEntry]:
        return self.investigation.journal

    def later(self, minutes: float = 5) -> None:
        self.clock.advance(minutes * 60)

    def open_leads(self) -> dict[str, list[str]]:
        return {entry.fact_id: [lead.fact_id for lead in entry.leads] for entry in self.entries}


def test_a_fact_told_becomes_an_entry_with_its_leads() -> None:
    notebook = Notebook()

    assert notebook.journal.told(GONE, ANA, "Ana", lie=False)

    assert notebook.entries == [
        JournalEntry(
            fact_id="gone",
            text="What happened: gone.",
            source=Source(kind=SourceKind.RESIDENT, id="ana", name="Ana"),
            learned=START,
            flushed=None,
            leads=GONE.leads,
        )
    ]


def test_a_lie_is_written_as_it_was_told_and_opens_no_leads() -> None:
    notebook = Notebook()

    assert notebook.journal.told(THERE, did(f'"{ALIBI}"'), "Ben", lie=True)

    [entry] = notebook.entries
    assert (entry.fact_id, entry.text, entry.leads) == ("there_ben", f"“{ALIBI}”", [])
    assert entry.source == Source(kind=SourceKind.RESIDENT, id="ben", name="Ben")


def test_any_entry_about_a_fact_closes_the_leads_to_it_and_none_reopen() -> None:
    notebook = Notebook()

    notebook.journal.told(GONE, ANA, "Ana", lie=False)
    notebook.journal.told(SEEN, SEEN.known_by[0], "Ana", lie=False)
    assert notebook.open_leads() == {"gone": ["notes"], "seen": ["there_ben"]}

    notebook.journal.told(THERE, THERE.known_by[0], "Ben", lie=True)
    assert notebook.open_leads() == {"gone": ["notes"], "seen": [], "there_ben": []}

    notebook.journal.found(NOTES, "Aris's notes")
    assert notebook.open_leads() == {"gone": [], "seen": [], "there_ben": [], "notes": []}


@pytest.mark.parametrize(("player", "lie", "truth"), [(Player(), None, None), (EYE, True, False)])
def test_the_eye_shows_a_flush_on_a_lie_and_none_on_the_truth(
    player: Player, lie: bool | None, truth: bool | None
) -> None:
    notebook = Notebook(player)

    notebook.journal.told(GONE, BEN, "Ben", lie=False)
    notebook.journal.told(ATTACK, ATTACK.known_by[0], "Ben", lie=True)
    notebook.journal.found(NOTES, "Aris's notes")

    assert [entry.flushed for entry in notebook.entries] == [truth, lie, None]


def test_the_eye_catches_a_lie_heard_before_it() -> None:
    notebook = Notebook()
    notebook.journal.told(GONE, ANA, "Ana", lie=False)
    notebook.journal.told(THERE, THERE.known_by[0], "Ben", lie=True)
    notebook.later()
    notebook.player = EYE

    assert notebook.journal.told(THERE, THERE.known_by[0], "Ben", lie=True)
    assert not notebook.journal.told(GONE, BEN, "Ben", lie=False)

    assert [(e.fact_id, e.source.id, e.flushed) for e in notebook.entries] == [
        ("gone", "ana", None),
        ("there_ben", "ben", True),
    ]
    assert notebook.entries[-1].learned == START + timedelta(minutes=5)


def test_what_the_journal_has_is_not_written_again() -> None:
    notebook = Notebook(EYE)
    journal = notebook.journal

    assert journal.told(GONE, ANA, "Ana", lie=False)
    assert not journal.told(GONE, BEN, "Ben", lie=False)
    assert journal.told(ATTACK, ATTACK.known_by[0], "Ben", lie=True)
    assert not journal.told(ATTACK, ATTACK.known_by[0], "Ben", lie=True)
    assert journal.told(ATTACK, saw("ana", 0.9, DEFLECTION), "Ana", lie=True)
    assert journal.found(NOTES, "Aris's notes")
    assert not journal.found(NOTES, "Aris's notes")

    assert [(e.fact_id, e.source.id) for e in notebook.entries] == [
        ("gone", "ana"),
        ("attack", "ben"),
        ("attack", "ana"),
        ("notes", NOTES),
    ]


def test_a_clue_holds_only_its_own_facts() -> None:
    notebook = Notebook()

    assert not notebook.journal.found("door_frame", "The splintered door frame")
    assert not Journal(Investigation(), lambda: START).found(NOTES, "Aris's notes")
    assert notebook.journal.found(NOTES, "Aris's notes")

    [entry] = notebook.entries
    assert entry.source == Source(kind=SourceKind.CLUE, id=NOTES, name="Aris's notes")
    assert (entry.text, entry.flushed) == ("What happened: notes.", None)


class Listening:
    """A recorder on the conversation tests' village, whose residents say `replies` if given."""

    def __init__(self, player: Player | None = None, *replies: str, **village: Any) -> None:
        if replies:
            village["provider"] = FakeProvider([f"{reply} [values: honesty]" for reply in replies])
        self.village = investigating(incident=INCIDENT, config=LONG_AGO, **village)
        self.notebook = Notebook(player)
        self.changes = 0
        self.recorder = Recorder(self.notebook.journal, lambda: self.village.players, self.changed)
        self.village.world.bus.subscribe(LineSpoken, self.recorder.on_spoken)

    def changed(self) -> None:
        self.changes += 1

    async def say(self, said: str, npc: str) -> None:
        self.village.players.say(said, npc)
        await self.village.run()

    def learned(self) -> list[tuple[str, str, str, bool | None]]:
        return [(e.fact_id, e.source.name, e.text, e.flushed) for e in self.notebook.entries]


@pytest.mark.anyio
async def test_what_a_resident_tells_is_written_as_they_speak_but_not_what_they_keep_back() -> None:
    listening = Listening()

    await listening.say("Lovely morning, isn't it?", "ana")
    assert listening.notebook.entries == [] and listening.changes == 0

    await listening.say("Did you see anything the night Aris was attacked?", "ana")

    assert listening.learned() == [
        ("gone", "Ana", "What happened: gone.", None),
        ("seen", "Ana", "What happened: seen.", None),
    ]
    assert listening.changes == 1


@pytest.mark.anyio
async def test_an_attacker_s_lie_is_written_once_said_and_the_eye_sees_them_flush() -> None:
    listening = Listening(EYE, f"Me? {ALIBI} Why do you ask?")
    listening.village.walk_to("ben", 1)

    await listening.say("Where were you the night Aris was attacked?", "ben")

    assert listening.learned() == [
        ("gone", "Ben", "What happened: gone.", False),
        ("there_ben", "Ben", f"“{ALIBI}”", True),
    ]
    assert listening.notebook.open_leads() == {"gone": ["notes", "seen"], "there_ben": []}


@pytest.mark.anyio
async def test_a_cover_of_two_sentences_is_written_once_on_the_second() -> None:
    listening = Listening(None, "I was fast asleep that night. I didn’t hear a THING!")
    after: list[list[str]] = []

    def spoken(event: LineSpoken) -> None:
        if event.line.speaker == "ana":
            after.append([entry.fact_id for entry in listening.notebook.entries])

    listening.village.world.bus.subscribe(LineSpoken, spoken)
    await listening.say("Did you hear anything the night Aris was attacked?", "ana")

    assert after == [["gone", "seen"], ["gone", "seen", "shouting"]]
    assert listening.notebook.entries[-1].text == f"“{ASLEEP}”"


@pytest.mark.anyio
async def test_turned_down_the_player_is_told_only_the_cover_said() -> None:
    attacker = make_npc("ben", "house_2", tradition=1.0, security=1.0)
    listening = Listening(None, f"{ALIBI} Now leave me be.", npcs=(attacker,))
    watched(listening.village, npcs=(attacker,))
    await listening.village.run()

    await listening.say("Where were you the night Aris was attacked?", "ben")

    talk = listening.village.players.talk()
    assert talk is not None and talk.refusing
    assert listening.learned() == [("there_ben", "Ben", f"“{ALIBI}”", None)]


@pytest.mark.parametrize(
    ("said", "words", "says_it"),
    [
        ("“I wasn’t there,” she said.", "I wasn't there.", True),
        ("I WAS AT HOME — all night!", "I was at home all night.", True),
        ("I was at home\nall night long, honestly.", "I was at home all night.", True),
        ("I was home all night.", "I was at home all night.", False),
        ("Nowhere near.", "where", False),
        ("Anything.", "...", False),
    ],
)
def test_says_holds_words_whatever_their_case_quotes_and_punctuation(
    said: str, words: str, says_it: bool
) -> None:
    assert says(said, words) is says_it


@pytest.mark.parametrize(
    ("dx", "map", "found"),
    [(0, None, True), (0.5, None, True), (0.6, None, False), (0, "maker_space_floor_1", False)],
)
def test_e_finds_a_clue_from_its_cell(dx: float, map: str | None, found: bool) -> None:
    notes, notebook, changed = load_story().clue(NOTES), Notebook(), []
    recorder = Recorder(notebook.journal, lambda: None, lambda: changed.append(1), clues=[notes])

    claim = recorder.claim(Point(notes.x + dx, notes.y, map or notes.map))
    if claim is not None:
        assert claim.distance == dx
        claim.take()

    assert [entry.fact_id for entry in notebook.entries] == (["notes"] if found else [])
    assert changed == ([1] if found else [])


LIFESPANS = ("behaviour", "economy", "memory", "protocol", "world")
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)


def make_app(make_package: Callable[[dict[str, str]], str]) -> Starlette:
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in LIFESPANS}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    files["story/lifespan.py"] = "from simile.story.lifespan import lifespan, running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(START))
    return app


def next_of(ws: Any, type: str) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == type:
            return message
    raise AssertionError(f"no {type}")


def test_the_journal_comes_on_connect_and_again_when_a_clue_is_found(
    make_package: Callable[[dict[str, str]], str],
) -> None:
    app = make_app(make_package)
    notes = load_story().clue(NOTES)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        greeted = [ws.receive_json() for _ in range(4)]
        client.portal.call(movement_of(app).track, PLAYER_ID, Point(notes.x, notes.y, notes.map))
        ws.send_json({"type": "pick_up"})
        found = next_of(ws, "journal")

    assert [m["type"] for m in greeted] == ["snapshot", "clock", "player_state", "journal"]
    assert greeted[3]["entries"] == []
    [entry] = found["entries"]
    assert entry["fact_id"] == "notes"
    assert entry["source"] == {"kind": "clue", "id": NOTES, "name": "Aris's notes"}
    assert entry["flushed"] is None and entry["leads"]


@pytest.mark.parametrize(
    ("x", "took"),
    [(3.4, "the notes"), (3.5, "the bun"), (3.6, "the bun")],
)
def test_e_takes_the_nearer_of_a_clue_and_a_pile_and_the_pile_on_a_tie(
    make_package: Callable[[dict[str, str]], str], x: float, took: str
) -> None:
    app = make_app(make_package)
    notes = load_story().clue(NOTES)
    pile = Pile(at=MapTile(map=notes.map, x=notes.x + 1, y=notes.y), items=[BUN])

    with TestClient(app) as client:
        player = player_of(app)

        def stand() -> None:
            player.left = [pile]
            movement_of(app).track(PLAYER_ID, Point(x, notes.y, notes.map))
            hub_of(app).receive(PickUpMessage().model_dump_json())

        client.portal.call(stand)
        journal = [entry.fact_id for entry in investigation_of(app).journal]

    if took == "the notes":
        assert (journal, BUN in player.items, player.left) == (["notes"], False, [pile])
    else:
        assert (journal, BUN in player.items, player.left) == ([], True, [])


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data" / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


@pytest.mark.anyio
async def test_the_journal_survives_a_restart(database: Path) -> None:
    notes = load_story().clue(NOTES)
    kept: list[JournalEntry] = []

    async def find_the_notes(app: Starlette) -> None:
        movement_of(app).track(PLAYER_ID, Point(notes.x, notes.y, notes.map))
        hub_of(app).receive(PickUpMessage().model_dump_json())
        kept.extend(investigation_of(app).journal)

    async def resumed(app: Starlette) -> None:
        assert investigation_of(app).journal == kept

    await run_village(find_the_notes)
    assert [entry.fact_id for entry in kept] == ["notes"]
    await run_village(resumed)
