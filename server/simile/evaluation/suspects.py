import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.prompt import (
    Cue,
    Player,
    background,
    duration,
    first_name,
    habits,
    jokes,
    rough_edges,
    system_prompt,
    turn_prompt,
)
from simile.conversation.telling import UNASKED, Stance, Telling, tellings, told
from simile.evaluation.play import Prompt
from simile.evaluation.scenarios import NOW, Scenario
from simile.llm import LLMClient
from simile.memory.store import SharedHistory
from simile.schema import PLAYER_ID, Bionic, HowKnown, Id, Incident, Line, Npc
from simile.social import looks, meet, strongly_against, tolerance, unease
from simile.story.content import load_story
from simile.story.incident import ATTACK, GRUDGE, MEETING, SEEN, SHOUTING, THERE, Made, build
from simile.story.suspects import attackers
from simile.story.writing import Backstory, drafted, write

PURPOSE = "evaluation-suspects"
SEEDS = (0, 1, 6, 7)
"""Incidents whose liars are all four suspects between them, with every kind of cover."""
EYE = Bionic.INFRARED_EYE
MISSING = "missing"
LATER = "later"
AFTER = "Fair enough. So what keeps you busy these days?"
ASKS = {
    THERE: "Where were you the night Aris was attacked?",
    ATTACK: "Do you know who attacked Aris?",
    f"{GRUDGE}{HowKnown.DID}": "How did you get on with Aris?",
    f"{GRUDGE}{HowKnown.WITNESSED}": "Did you ever see anyone row with Aris?",
    SHOUTING: "Did you hear anything the night Aris was attacked?",
    SEEN: "Did you see anyone the night Aris was attacked?",
    MEETING: "I heard you saw some people together the evening before Aris was attacked. Who "
    "was it?",
    MISSING: "Is it true Aris has gone missing? Her workshop's standing open.",
}
STANCES = {
    "covers": "gives a cover story: where they were, that they saw, heard or know nothing, or "
    "that they got on fine with her",
    "admits": "lets slip or owns up to something the situation says they're hiding",
    "evades": "dodges the question or says they'd rather not talk about it, with no cover story",
    "answers": "answers or chats about what was asked, which they have nothing to hide about",
    "refuses": "turns the visitor down, or won't talk to them at all",
}


@dataclass(frozen=True)
class Case:
    """A liar in one of S12's incidents answering the player's last line, as B5 would."""

    id: str
    seed: int
    npc: Npc
    role: str
    """`attacker` or `witness`."""
    said: tuple[str, ...]
    """The player's lines and the resident's in turn, ending with the player's."""
    asks: Id | None
    """The fact whose cover the player's last line asks for."""
    covers: dict[Id, str]
    """Every cover they were given, by fact id."""
    refusing: bool
    tellings: tuple[Telling, ...]
    hidden: str
    """What they're hiding, for the judges."""

    @property
    def cover(self) -> str | None:
        return self.covers.get(self.asks) if self.asks else None

    @property
    def line(self) -> str:
        return self.said[-1]


def ask_for(fact_id: Id, how: HowKnown) -> str:
    if fact_id.startswith(THERE):
        return ASKS[THERE]
    if fact_id.startswith(GRUDGE):
        return ASKS[f"{GRUDGE}{how}"]
    return ASKS[fact_id]


def incident(
    npcs: Sequence[Npc], seed: int, backstory: Backstory | None = None, now: datetime = NOW
) -> Made:
    """S12's incident for `seed` as `make_incident` draws it, with `backstory` or the templates'."""
    rng, content = random.Random(seed), load_story()
    found = attackers(npcs, content.grievances, rng)
    met = rng.choice(content.meeting_places)
    story = backstory or drafted(found, content)
    return build(npcs, found, story, now, rng, content, met=met, written=backstory is not None)


async def written(llm: LLMClient, npcs: Sequence[Npc], seed: int) -> Backstory | None:
    """The backstory a new world's one Sonnet call writes for `seed`, or None if it fails."""
    rng, content = random.Random(seed), load_story()
    found = attackers(npcs, content.grievances, rng)
    met = rng.choice(content.meeting_places)
    backstory, ok = await write(llm, found, content, met=met)
    return backstory if ok else None


def uneasy(npc: Npc) -> bool:
    """Whether the player's infrared eye puts them off, so S11 has them turn the player down."""
    return unease(tolerance(npc.values), [EYE]) > 0


def cases(made: Made, npcs: Sequence[Npc], seed: int) -> list[Case]:
    """Each liar asked for each cover, asked something no cover answers, and refusing if uneasy."""
    by = {npc.id: npc for npc in npcs}
    found: list[Case] = []
    refusals = seed
    for n, npc in enumerate(liars(made.incident, npcs)):
        refuse = None
        if uneasy(npc):
            refuse, refusals = refusals % 2 == 0, refusals + 1
        found += questioned(made, by, npc, seed, later=n % 2 == 1, refuse=refuse)
    return found


def questioned(
    made: Made, by: dict[Id, Npc], npc: Npc, seed: int, *, later: bool, refuse: bool | None
) -> list[Case]:
    """`npc` asked for each cover, then for none, then refusing, for a cover if `refuse`."""
    trust = meet(npc, PLAYER_ID).trust
    memories = [memory for memory in made.memories if memory.owner == npc.id]
    theirs = tellings(made.incident, npc.id, trust, memories)
    lying = [t for t in theirs if t.stance is Stance.LIE]
    role = "attacker" if npc.id in made.incident.attackers else "witness"
    covers = {t.fact.id: t.knower.cover or "" for t in lying}
    hidden = hiding(made.incident, by, npc, lying)

    def case(said: tuple[str, ...], asks: Id | None, kind: str, refusing: bool = False) -> Case:
        shown = tuple(t for t in theirs if not refusing or t.stance is Stance.LIE)
        name = f"{seed}/{npc.id}/{kind}{'/refused' if refusing else ''}"
        return Case(name, seed, npc, role, said, asks, covers, refusing, shown, hidden)

    found = [
        case((ask_for(t.fact.id, t.knower.how),), t.fact.id, t.fact.id.split("_")[0]) for t in lying
    ]
    main = next((t for t in lying if t.fact.id.startswith(THERE)), lying[0])
    question, kind = ask_for(main.fact.id, main.knower.how), main.fact.id.split("_")[0]
    if later:
        found.append(case((question, covers[main.fact.id], AFTER), None, LATER))
    else:
        found.append(case((ASKS[MISSING],), None, MISSING))
    if refuse:
        found.append(case((question,), main.fact.id, kind, refusing=True))
    elif refuse is not None:
        found.append(case((ASKS[MISSING],), None, MISSING, refusing=True))
    return found


def liars(made: Incident, npcs: Sequence[Npc]) -> list[Npc]:
    """Residents who'd lie about something to a newcomer, by their trust in one, in id order."""
    return [
        npc
        for npc in sorted(npcs, key=lambda npc: npc.id)
        if any(t.stance is Stance.LIE for t in tellings(made, npc.id, meet(npc, PLAYER_ID).trust))
    ]


def hiding(made: Incident, by: dict[Id, Npc], npc: Npc, lying: Sequence[Telling]) -> str:
    name = first_name(npc)
    others = [first_name(by[id]) for id in made.attackers if id != npc.id]
    parts = []
    if npc.id in made.attackers:
        withs = f" with {' and '.join(others)}" if others else ""
        parts.append(f"{name} secretly attacked Aris{withs} and smashed up her workshop.")
    parts += [f"Hidden: {telling.fact.what}" for telling in lying if telling.fact.id != ATTACK]
    return " ".join(parts)


def prompt(case: Case, config: ConversationConfig = DEFAULT_CONFIG, now: datetime = NOW) -> Prompt:
    """B5's prompts for the case's reply, as `PlayerConversations` writes them once asked."""
    npc, player = case.npc, Player()
    seen = looks(player.name, [EYE], tolerance(npc.values), [EYE]) if case.refusing else None
    known = background(
        npc, player, meet(npc, PLAYER_ID), SharedHistory([], []), [], [], None, now, looks=seen
    )
    lying = [t for t in case.tellings if t.stance is Stance.LIE]
    lies = [t.temptation().direction() for t in lying] + ([UNASKED] if lying else [])
    joke = jokes(npc.humour, f"{PURPOSE}/{case.id}")
    text = turn_prompt(
        known,
        conversation(case, now, config),
        {PLAYER_ID: player.name, npc.id: first_name(npc)},
        Cue.REFUSE if case.refusing else Cue.REPLY,
        player.name,
        config,
        speaker=npc.id,
        facts=told(case.tellings, player.name),
        lies=lies,
        joke=joke,
        blunt=case.refusing and strongly_against(npc),
    )
    spoken = (first_name(npc), npc.name)
    return Prompt(system_prompt(npc, config), text, spoken, (player.name,), tuple(lies), joke)


def conversation(case: Case, now: datetime, config: ConversationConfig) -> list[Line]:
    start = now - timedelta(seconds=20 * len(case.said))
    return [
        Line(
            id=n,
            conversation_id=PURPOSE,
            speaker=PLAYER_ID if n % 2 == 0 else case.npc.id,
            text=text,
            timestamp=start + timedelta(seconds=20 * n),
            duration=duration(text, config),
        )
        for n, text in enumerate(case.said)
    ]


def sketch(npc: Npc) -> str:
    """Who the resident is and how they speak, for the in-character judge."""
    said = f" Their verbal habits: {habits(npc)}." if npc.mannerisms else ""
    edges = "".join(f" {edge}" for edge in rough_edges(npc, first_name(npc)))
    return (
        f"{npc.name}, {npc.age}, {npc.occupation}. {npc.persona} How they speak: "
        f"{npc.speaking_style}{said}{edges}"
    )


def scenario(case: Case) -> Scenario:
    """The case as the judge's situation, with what they'll tell and what they're hiding."""
    npc, player = case.npc, Player()
    name = first_name(npc)
    known = "".join(
        f" {name} knows this, and may tell it: {t.fact.what}"
        for t in case.tellings
        if t.stance is Stance.TELL
    )
    before = ""
    if len(case.said) > 1:
        before = f' Earlier the visitor asked "{case.said[0]}" and {name} said "{case.said[1]}".'
    turned = " Bionics put them off, and they're turning the visitor down." if case.refusing else ""
    return Scenario(
        id=case.id,
        title=case.id,
        situation=f"{npc.name}, {npc.occupation}, is talking to the visitor, a newcomer to the "
        f"village.{known} {case.hidden}{before}{turned}",
        name=player.name,
        description=player.description,
        line=case.line,
        stances=STANCES,
    )
