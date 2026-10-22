import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from simile.characters.humour import describe_humour
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.needs import feels
from simile.memory import SharedHistory
from simile.news.reactions import TITLE
from simile.schema import (
    PLAYER_ID,
    CoreValue,
    FlagKind,
    Humour,
    Id,
    Line,
    Memory,
    Npc,
    Relationship,
    Work,
)
from simile.social import describe
from simile.voice import SpeakingRate


class Cue(StrEnum):
    """What the line being written is for."""

    OPEN = "open"
    REPLY = "reply"
    GOODBYE = "goodbye"
    FAREWELL = "farewell"
    REFUSE = "refuse"


SETTING_OFF = "If you've said you'll go and do something now, say where you're off to."
CUES: dict[Cue, str] = {
    Cue.OPEN: "You've just walked up to {other}. Say hello and start the conversation.",
    Cue.REPLY: "Say your next line to {other}. Keep the conversation going: don't wrap it up or "
    "say goodbye yet.",
    Cue.GOODBYE: "You've had enough of this conversation. Wrap it up now with a brief, natural "
    f"goodbye to {{other}}. {SETTING_OFF}",
    Cue.FAREWELL: f"{{other}} is leaving. Say a brief goodbye back. {SETTING_OFF}",
    Cue.REFUSE: "You'd rather not talk to {other}. Turn them down in a few words, and leave it "
    "there.",
}
BLUNT = "Tell them why in one curt line: you don't hold with bionics."
POLITE = "Keep it polite, and keep your reason to yourself."
COVERED = "If they asked what one of your cover stories answers, give it as you turn them down."
JOKE = "Work a joke into this line, in your own humour."
PLAIN = "No joke in this line: say it plainly."
OFF_TO = (
    "You need to {errand}. Wrap it up now with a brief, natural goodbye to {other}, and say why "
    "you're going."
)

THEIR_FLAGS: dict[FlagKind, str] = {
    FlagKind.DEBT: "You still owe {name} for {description}.",
    FlagKind.GRUDGE: "{name} holds a grudge against you over {description}.",
    FlagKind.PROMISE: "You promised {name}: {description}.",
    FlagKind.BROKEN_PROMISE: "{name} knows you broke a promise: {description}.",
    FlagKind.SAVED_LIFE: "You once saved {name}'s life: {description}.",
    FlagKind.SECRET: "You told {name} a secret: {description}.",
}

VALUE_NAMES = ", ".join(value.value.replace("_", " ") for value in CoreValue)
VALUES = {value.value for value in CoreValue}

LOW = (0.4, 0.25, 0.15)
HIGH = 0.6
EDGES: dict[CoreValue, tuple[str, str, str]] = {
    CoreValue.HONESTY: (
        "{who} will shade the truth when it suits {them}, and won't always say everything "
        "{they} know.",
        "{who} will lie when it suits {them}: white lies, convenient excuses, keeping back what "
        "{they}'d rather not say.",
        "{who} will lie easily, without guilt, whenever it suits {them}: white lies, convenient "
        "excuses, keeping back whatever {they}'d rather not say.",
    ),
    CoreValue.COMPASSION: (
        "{who} won't go out of {their} way to soften bad news.",
        "{who} won't soften bad news, will be short with complaints, and will put {their} own "
        "interests first.",
        "{who} won't soften anything, will have no patience for complaints, and will put {their} "
        "own interests first every time.",
    ),
    CoreValue.PEACE_OF_MIND: (
        "{who} will say so when {they} disagree.",
        "{who} will disagree openly and won't give ground just to keep the peace.",
        "{who} will disagree bluntly, won't concede anything to keep the peace, and can be curt "
        "or change the subject.",
    ),
}
SAYS_NO = (
    "{who} can turn down a favour without feeling bad about it.",
    "{who} will turn down favours and say no without apologising.",
    "{who} will turn down most favours and say no without apologising.",
)
COUNTERWEIGHT = (
    "Don't agree just to be pleasant. Saying no, being brief, or disagreeing is fine when it's in "
    "character."
)
BOUNDS = (
    "Keep to the game's tone: no slurs, abuse or cruelty, and rudeness means curtness, never "
    "insults. Any lie stays small and in character: about {who}, {their} reasons, plans or what "
    "{they} did or saw. Never make up facts about the village, its places, times or people."
)

TAG = re.compile(
    r"\[\s*values?\s*:([^\]\n]*)\]?|^\s*values?\s*:(.*)$|\[([^\]\n]*)\]",
    re.IGNORECASE | re.MULTILINE,
)
CUT_OFF = re.compile(r"\[[^\]\n]*$")
STAGE_DIRECTION = re.compile(r"\*[^*]*\*")
QUOTES = {'"': '"', "“": "”", "'": "'"}
FAREWELL = (
    r"(?:good-?\s?bye|bye(?:-bye| now| then| for now)?|cheerio|ciao|farewell|good\s?night|"
    r"take care(?: now| then| of yourself)?)"
)
CLAUSE_START = r"(?:^|[,;:—-]\s*|\b(?:and|so|well|right|okay|ok|anyway)\s+)"
CLAUSE_END = r"(?=\s*(?:[,.!…]|$))"
SEE_YOU = r"see (?:you|ya)\b(?!['’])"
LOOKED_AFTER = rf" (?:(?:out|off|home|through)\b(?! there)|right{CLAUSE_END})"
LEAVING = re.compile(
    rf"{CLAUSE_START}{FAREWELL}{CLAUSE_END}"
    rf"|{CLAUSE_START}{SEE_YOU}|\b(?:i|we)(?:['’]ll| will| shall) {SEE_YOU}(?!{LOOKED_AFTER})"
    rf"|\bsee (?:you|ya) (?:later|soon|around|tomorrow){CLAUSE_END}"
    r"|\bcatch (?:you|ya) (?:later|soon|around)\b"
    r"|\btalk (?:to you )?(?:later|soon)\b|\buntil next time\b|\bmind how you go\b"
    r"|\bgood (?:day|morning|afternoon|evening) to you\b(?! too)"
    r"|\b(?:i['’]ll|i will|i shall|i['’]d better|i['’]d best|i should|i must|let me) "
    r"(?:leave you (?:to|be|in peace)|let you get|be off|get going|head off|be on my way)\b"
    r"|\b(?:must|gotta|got to|have to) (?:dash|be off|get going)\b|\boff i go\b",
    re.IGNORECASE,
)
SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+")
ABBREVIATION = re.compile(r"\b(?:mr|mrs|ms|dr|st|prof|vs|etc|e\.g|i\.e)\.$", re.IGNORECASE)
OPENING_WORDS = 3
OPENINGS = 4


@dataclass(frozen=True)
class Player:
    """The player as NPCs see them. B3 calls them Visitor too."""

    name: str = "Visitor"
    description: str = "a newcomer to the village"
    id: Id = PLAYER_ID


@dataclass(frozen=True)
class Draft:
    """A line as written: its spoken text and the core values it touches."""

    text: str
    values: tuple[CoreValue, ...] = ()


@dataclass(frozen=True)
class WorkTopic:
    """A work someone might bring up: their memory of making, reading or seeing it."""

    memory: Memory
    work: Work


def first_name(person: Npc | Player) -> str:
    return person.name if isinstance(person, Player) else person.name.split()[0]


def system_prompt(npc: Npc, config: ConversationConfig = DEFAULT_CONFIG) -> str:
    """Who the resident is and how to answer the player. The same for every line they say."""
    ranked = sorted(npc.values.items(), key=lambda item: -item[1])
    most = ", ".join(value_name(value) for value, _ in ranked[:5])
    least = ", ".join(value_name(value) for value, _ in reversed(ranked[-3:]))
    bounds = BOUNDS.format(who="yourself", their="your", they="you")
    return "\n\n".join(
        [
            f"You are {npc.name}, aged {npc.age}. Occupation: {npc.occupation}. You live in a "
            "small, modern village. Stay in character.",
            npc.persona,
            npc.backstory,
            how_you_speak(npc),
            f"What you care about most: {most}. What you care about least: {least}.\n"
            f"Your interests: {', '.join(npc.interests)}.",
            " ".join([*rough_edges(npc), COUNTERWEIGHT, bounds]),
            "You're in a face-to-face conversation. Reply with only your next spoken line: at "
            f"most {config.max_words} words, usually one or two sentences. Plain speech: no "
            "stage directions, quotation marks or name label. React to what was just said and "
            "don't repeat yourself.",
            "You know what someone with your life and job would know. Outside that, ask, admit "
            "you don't know, or give your own angle rather than expert advice. This is a chat "
            "between neighbours, not a consultation: listen and react more than you advise. If "
            "they want to change the subject, go with it, or say once that you'd rather not and "
            "let it go.",
            "After the line, on a last line of its own, list the one to three core values the "
            "conversation is touching now, like this: [values: honesty, ambition]\n"
            f"Choose from: {VALUE_NAMES}.",
        ]
    )


def rough_edges(npc: Npc, name: str | None = None) -> list[str]:
    """How their low scores show in what they say, more the lower they are, told to them or, with
    `name`, about them. Empty when none is low."""
    words = (
        {"who": name, "they": "they", "them": "them", "their": "their"}
        if name
        else {"who": "You", "they": "you", "them": "you", "their": "your"}
    )
    levels = {value: sum(npc.values[value] < bar for bar in LOW) for value in EDGES}
    found = [EDGES[value][level - 1] for value, level in levels.items() if level]
    unkind = levels[CoreValue.COMPASSION]
    if unkind and npc.values[CoreValue.SELF_RESPECT] >= HIGH:
        found.append(SAYS_NO[unkind - 1])
    return [line.format(**words) for line in found]


def how_you_speak(npc: Npc) -> str:
    style = f"How you speak: {npc.speaking_style}"
    if not npc.mannerisms:
        spoken = f"{style} Use your pet words and phrases now and then, not in every line."
    else:
        spoken = (
            f"{style}\nYour verbal habits: {habits(npc)}. Use these now and then, not in every "
            "line, and the same goes for your pet words and phrases."
        )
    return f"{spoken}\n{describe_humour(npc.humour, kind=True)}" if npc.humour else spoken


def habits(npc: Npc) -> str:
    return "; ".join(mannerism.rstrip(".") for mannerism in npc.mannerisms)


def background(
    speaker: Npc,
    other: Npc | Player,
    rel: Relationship,
    history: SharedHistory,
    memories: Sequence[Memory],
    topics: Sequence[Memory],
    place: str | None,
    now: datetime,
    plans: str = "",
    *,
    looks: str | None = None,
) -> str:
    """What the speaker knows going in: the other person, their history, what they could plan
    to do and have said they will, and what's on their mind."""
    name = first_name(other)
    where = f"at {place}" if place else "out in the street"
    who = (
        other.description
        if isinstance(other, Player)
        else f"{other.name}, aged {other.age}, {other.occupation}"
    )
    meeting = f"It's {now:%H:%M}, {where}. You're with {name} ({who})."
    parts = [f"{meeting} {looks}" if looks else meeting, describe(rel, name)]
    events = [
        f"- {ago(event.timestamp, now)}, {'you' if event.actor == speaker.id else name}: "
        f"{event.action}"
        for event in history.events
    ]
    flags = [
        THEIR_FLAGS[flag.kind].format(name=name, description=flag.description.strip().rstrip("."))
        for flag in history.flags
        if flag.owner == other.id and flag.about == speaker.id
    ]
    if events:
        parts.append("Between you two:\n" + "\n".join(events))
    parts += flags
    if plans:
        parts.append(plans)
    if memories:
        parts.append("On your mind:\n" + "\n".join(f"- {m.content}" for m in memories))
    if topics:
        parts.append("News you might bring up:\n" + "\n".join(f"- {m.content}" for m in topics))
    return "\n\n".join(parts)


def turn_prompt(
    background: str,
    lines: Sequence[Line],
    names: Mapping[Id, str],
    cue: Cue,
    other: str,
    config: ConversationConfig = DEFAULT_CONFIG,
    *,
    speaker: Id | None = None,
    recalled: Sequence[Memory] = (),
    works: Sequence[WorkTopic] = (),
    mood: Sequence[str] = (),
    errand: str | None = None,
    detail: Memory | None = None,
    facts: Sequence[str] = (),
    lies: Sequence[str] = (),
    joke: bool | None = None,
    blunt: bool = False,
) -> str:
    """The speaker's next line, with their mood, article `detail`, `facts`, `lies` and `joke`."""
    recent = lines[-config.transcript_lines :]
    if recent:
        transcript = "\n".join(f"{names[line.speaker]}: {line.text}" for line in recent)
        if len(lines) > len(recent):
            transcript = f"...\n{transcript}"
        so_far = f"The conversation so far:\n{transcript}"
    else:
        so_far = "The conversation hasn't started yet."
    parts = [background, feels("you", mood)] if mood else [background]
    parts += [*facts, *lies, *your_works(works, speaker), so_far]
    if recalled:
        parts.append(
            f"You read about what {other} just mentioned:\n"
            + "\n".join(f"- {m.content}" for m in recalled)
        )
    if detail is not None and detail.points:
        parts.append(stuck(detail))
    openings = [opening(line.text) for line in lines if line.speaker == speaker][-OPENINGS:]
    if openings:
        listed = ", ".join(f'"{words}..."' for words in openings)
        parts.append(
            f"Your lines so far began {listed}. Begin this one another way, and don't greet "
            f"{other} again."
        )
    if joke is not None:
        parts.append(JOKE if joke else PLAIN)
    parts.append(f"Say one or two sentences, at most {config.max_words} words.")
    asked = CUES[cue].format(other=other)
    if cue is Cue.GOODBYE and errand:
        asked = OFF_TO.format(errand=errand, other=other)
    elif cue is Cue.REFUSE:
        asked = " ".join([asked, BLUNT if blunt else POLITE, *([COVERED] if lies else [])])
    return "\n\n".join([*parts, asked])


def jokes(humour: Humour | None, seed: str, *, after_joke: bool = False) -> bool | None:
    """Whether a line jokes, as often as their seriousness leaves room for, the same each time
    for the same `seed`, and never straight `after_joke`. None without a humour."""
    if humour is None:
        return None
    return not after_joke and random.Random(seed).random() < 1 - humour.seriousness


def detailed(*memories: Sequence[Memory]) -> Memory | None:
    """The first of `memories` with points: the one article whose points a prompt gives."""
    return next((memory for group in memories for memory in group if memory.points), None)


def stuck(memory: Memory, who: str = "you") -> str:
    title = TITLE.match(memory.content)
    article = f'"{title[1]}"' if title else f"what {who} read"
    points = "\n".join(f"- {point}" for point in memory.points)
    return f"What stuck with {who} from {article}:\n{points}"


def your_works(works: Sequence[WorkTopic], speaker: Id | None) -> list[str]:
    own = [f"- {topic.memory.content}" for topic in works if topic.work.artist == speaker]
    others = [f"- {topic.memory.content}" for topic in works if topic.work.artist != speaker]
    parts = []
    if own:
        parts.append("Your own works, which you might bring up and stand by:\n" + "\n".join(own))
    if others:
        parts.append("Works by others you might bring up:\n" + "\n".join(others))
    return parts


def opening(text: str) -> str:
    return " ".join(text.split()[:OPENING_WORDS]).rstrip(",;:.!?—-")


def takes_leave(text: str) -> bool:
    """Whether the line ends by saying goodbye: its last sentence takes leave and isn't a
    question."""
    last = SENTENCE_BREAK.split(text.strip())[-1]
    if last.rstrip("\"'”’)]* ").endswith("?"):
        return False
    return LEAVING.search(last) is not None


def parse_reply(
    text: str,
    names: Sequence[str] = (),
    others: Sequence[str] = (),
    config: ConversationConfig = DEFAULT_CONFIG,
) -> Draft:
    """The speaker's line and its values from a reply, without the tag, labels, stage directions
    or any turn written for `others`, and without sentences that start past `max_words`."""
    values: tuple[CoreValue, ...] = ()
    for match in TAG.finditer(text):
        found = _values(match.group(1) or match.group(2) or match.group(3) or "")
        if found or match.group(3) is None:
            values = found
    spoken = CUT_OFF.sub("", TAG.sub(_untag, text).rstrip())
    for name in others:
        turn = re.search(rf"^\s*{re.escape(name)}\s*:", spoken, re.IGNORECASE | re.MULTILINE)
        if turn:
            spoken = spoken[: turn.start()]
    spoken = " ".join(STAGE_DIRECTION.sub(" ", spoken).split())
    for name in sorted(names, key=len, reverse=True):
        if spoken.lower().startswith(f"{name.lower()}:"):
            spoken = spoken[len(name) + 1 :].strip()
            break
    if len(spoken) >= 2 and QUOTES.get(spoken[0]) == spoken[-1]:
        spoken = spoken[1:-1].strip()
    return Draft(_trim(spoken, config.max_words), values)


def duration(
    text: str, config: ConversationConfig = DEFAULT_CONFIG, rate: SpeakingRate | None = None
) -> float:
    """Seconds to say `text` aloud: at the voice's measured rate, or else at the configured pace."""
    seconds = rate.seconds(text) if rate else len(text.split()) * 60 / config.words_per_minute
    return max(config.min_line_seconds, seconds)


def _trim(text: str, max_words: int) -> str:
    """`text` without the sentences that start after its first `max_words` words."""
    for match in SENTENCE_BREAK.finditer(text):
        if len(text[: match.start()].split()) >= max_words and not ABBREVIATION.search(
            text, 0, match.start()
        ):
            return text[: match.start()]
    return text


def _untag(match: re.Match[str]) -> str:
    """A values tag gone, and brackets that name no core value, like "[laughs]", kept."""
    bare = match.group(3)
    return match.group(0) if bare is not None and not _values(bare) else " "


def _values(listed: str) -> tuple[CoreValue, ...]:
    found: list[CoreValue] = []
    for name in listed.split(","):
        key = re.sub(r"[\s-]+", "_", name.strip().strip(".").lower())
        if key in VALUES and CoreValue(key) not in found:
            found.append(CoreValue(key))
    return tuple(found)


def value_name(value: CoreValue) -> str:
    return value.value.replace("_", " ")


def ago(then: datetime, now: datetime) -> str:
    elapsed = now - then
    if elapsed < timedelta(hours=1):
        return "just now"
    if elapsed < timedelta(days=1):
        hours = int(elapsed / timedelta(hours=1))
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    days = elapsed.days
    return "yesterday" if days == 1 else f"{days} days ago"
