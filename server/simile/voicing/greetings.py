"""Recorded greetings, which the client plays as a resident starts talking to the player."""

import hashlib
import json
import re
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field, TypeAdapter

from simile.schema import Character, CoreValue, Id, Model, Npc
from simile.voicing import speak

if TYPE_CHECKING:
    from simile.library import Library

REPO_ROOT = Path(__file__).resolve().parents[3]
GREETINGS = REPO_ROOT / "content" / "voices" / "greetings"
LINES = GREETINGS / "lines.json"
MADE = GREETINGS / "made.json"
CHOSEN = REPO_ROOT / "content" / "voices" / "elevenlabs.json"
SYNTHESIS = 1
"""Bump it when a change to how greetings are said or encoded should make them all again."""
SUFFIX = ".m4a"


class Engine(StrEnum):
    ELEVENLABS = "elevenlabs"
    LOCAL = "local"


class Greeting(Model):
    text: str = Field(min_length=1, max_length=40)
    take: int = Field(default=0, ge=0, description="Another take of the same words, if one's off.")


class Chosen(Model):
    """A resident's voice from the ElevenLabs library, for their prerecorded clips."""

    voice: str = Field(min_length=1, description="The ElevenLabs voice id.")
    name: str = Field(min_length=1, description="Its name in the library.")
    accent: str = Field(min_length=1)
    delivery: str = Field(default="", description='Audio tags said before each line: "[warmly]".')


class Made(Model):
    engine: Engine
    digests: list[str] = Field(description="Each line's `digests` entry when it was said.")
    seconds: list[float]


_lines = TypeAdapter(dict[Id, list[Greeting]])
_chosen = TypeAdapter(dict[Id, Chosen])
_made = TypeAdapter(dict[Id, Made])


def load_lines(path: Path | None = None) -> dict[Id, list[Greeting]]:
    return _lines.validate_json((path or LINES).read_bytes())


def load_chosen(path: Path | None = None) -> dict[Id, Chosen]:
    return _chosen.validate_json((path or CHOSEN).read_bytes())


def load_made(path: Path | None = None) -> dict[Id, Made]:
    path = path or MADE
    return _made.validate_json(path.read_bytes()) if path.exists() else {}


def save_made(made: Mapping[Id, Made], path: Path | None = None) -> None:
    dumped = {id: made[id].model_dump(mode="json") for id in sorted(made)}
    (path or MADE).write_text(json.dumps(dumped, indent=2) + "\n", encoding="utf-8")


def said(line: Greeting, engine: Engine, chosen: Chosen | None) -> str:
    """The text sent to the engine, with an ElevenLabs voice's delivery before it."""
    if engine is Engine.LOCAL or chosen is None:
        return line.text
    return f"{chosen.delivery} {line.text}".strip()


def digests(
    npc: Npc, lines: Sequence[Greeting], engine: Engine, chosen: Chosen | None
) -> list[str]:
    """One per line, which changes with its words, take, voice, engine or `SYNTHESIS`."""
    if engine is Engine.ELEVENLABS:
        if chosen is None:
            raise ValueError(f"{npc.id} has no ElevenLabs voice")
        from simile.voicing.eleven import MODEL

        voice, clip = f"{MODEL}/{chosen.voice}", b""
    else:
        if npc.voice.reference_clip is None:
            raise ValueError(f"{npc.id}'s voice has no reference clip")
        voice, clip = npc.voice.reference_line, (REPO_ROOT / npc.voice.reference_clip).read_bytes()
    return [
        hashlib.sha256(
            f"greetings {SYNTHESIS}\n{engine}\n{voice}\n{line.take}\n"
            f"{said(line, engine, chosen)}\n".encode()
            + clip
        ).hexdigest()
        for line in lines
    ]


def stale(
    npc: Npc,
    lines: Sequence[Greeting],
    made: Made | None,
    engine: Engine,
    chosen: Chosen | None,
) -> list[int]:
    """The lines to say again in `engine`: changed, missing, or made with the other one."""
    have = made.digests if made is not None and made.engine is engine else []
    wanted = digests(npc, lines, engine, chosen)
    return [n for n, digest in enumerate(wanted) if n >= len(have) or have[n] != digest]


def current(npc: Npc, lines: Sequence[Greeting], made: Made | None, chosen: Chosen | None) -> bool:
    """Whether the greetings made are all of the lines, in the engine they were made with."""
    if made is None:
        return False
    try:
        return made.digests == digests(npc, lines, made.engine, chosen)
    except ValueError:
        return False


def outdated(
    npcs: Iterable[Npc],
    lines: Mapping[Id, list[Greeting]],
    made: Mapping[Id, Made],
    chosen: Mapping[Id, Chosen],
    engine: Callable[[Npc], Engine],
) -> list[Npc]:
    """Those whose greetings don't match their lines, or could now be made with ElevenLabs."""
    return [
        npc
        for npc in npcs
        if npc.id in lines
        and (npc.id in chosen or npc.voice.reference_clip is not None)
        and (
            not current(npc, lines[npc.id], made.get(npc.id), chosen.get(npc.id))
            or (engine(npc) is Engine.ELEVENLABS and made[npc.id].engine is Engine.LOCAL)
        )
    ]


type Say = Callable[[str, int], Any]
"""Says a text with a seed, as float samples at `speak.SAMPLE_RATE`."""


def record(
    npc: Npc,
    lines: Sequence[Greeting],
    made: dict[Id, Made],
    engine: Engine,
    chosen: Chosen | None,
    say: Say,
    folder: Path,
    *,
    force: bool = False,
    audition: bool = False,
    path: Path | None = None,
) -> list[tuple[str, float]]:
    """Says the stale lines, or only the first with `audition`, saving `made` after each."""
    before = made.get(npc.id)
    kept = before if before is not None and before.engine is engine and not force else None
    todo = stale(npc, lines, kept, engine, chosen)
    wanted = digests(npc, lines, engine, chosen)
    have = list(kept.digests[: len(lines)]) if kept else []
    seconds = list(kept.seconds[: len(lines)]) if kept else []
    spoken = []
    for n in [n for n in todo if n == 0] if audition else todo:
        line = lines[n]
        audio = say(said(line, engine, chosen), speak.seed(line.take, npc.id, line.text))
        speak.encode(audio, folder / f"{npc.id}_{n + 1}{SUFFIX}")
        length = round(len(audio) / speak.SAMPLE_RATE, 2)
        if n < len(have):
            have[n], seconds[n] = wanted[n], length
        else:
            have.append(wanted[n])
            seconds.append(length)
        made[npc.id] = Made(engine=engine, digests=have, seconds=seconds)
        save_made(made, path)
        spoken.append((line.text, length))
    if not audition:
        for extra in files(folder, npc.id)[len(lines) :]:
            extra.unlink()
        made[npc.id] = Made(engine=engine, digests=have, seconds=seconds)
        save_made(made, path)
    return spoken


def files(folder: Path, id: str) -> list[Path]:
    """`<id>_1.m4a`, `<id>_2.m4a` and so on in `folder`, in order."""
    pattern = re.compile(rf"{re.escape(id)}_[1-9]\{SUFFIX}")
    return sorted(path for path in folder.glob(f"{id}_*{SUFFIX}") if pattern.fullmatch(path.name))


def remove(folder: Path, id: str) -> None:
    for path in files(folder, id):
        path.unlink(missing_ok=True)


def players(library: "Library") -> Path:
    """Where the player's own characters' greetings are kept, beside their clips."""
    return library.root / "greetings"


def found(id: str, library: "Library") -> list[Path]:
    """A resident's greetings, or a player character's made since its clip last changed."""
    from simile.library import NotFound

    if committed := files(GREETINGS, id):
        return committed
    try:
        character = library.get(id)
    except NotFound:
        return []
    clip = library.clip(character)
    if library.is_premade(id) or clip is None or not clip.is_file():
        return []
    made = files(players(library), id)
    changed = clip.stat().st_mtime_ns
    return made if all(path.stat().st_mtime_ns >= changed for path in made) else []


TONES: dict[str, tuple[str, ...]] = {
    "formal": (
        "Excuse me. A word, please.",
        "Hello there. Have you a moment?",
        "Pardon me, a quick word?",
        "Good to see you.",
    ),
    "warm": (
        "Hello there! How are you?",
        "Hi! Got a minute?",
        "There you are! How's your day?",
        "Hey, good to see you!",
    ),
    "brisk": (
        "Got a minute?",
        "Quick word?",
        "You there. A moment.",
        "Hey. A quick question.",
    ),
    "playful": (
        "Hey! Over here!",
        "Psst! Got a sec?",
        "Hey, you! Come and see!",
        "Oi, over here!",
    ),
}
LEANINGS: dict[str, tuple[CoreValue, ...]] = {
    "formal": (CoreValue.OBEDIENCE, CoreValue.TRADITION, CoreValue.DISCIPLINE),
    "warm": (CoreValue.CONNECTION, CoreValue.COMPASSION, CoreValue.EQUALITY),
    "brisk": (CoreValue.SUCCESS, CoreValue.AMBITION, CoreValue.INDEPENDENCE),
    "playful": (CoreValue.ADVENTURE, CoreValue.PLEASURE, CoreValue.OPTIMISM),
}
HELLOS = (
    "kia orana",
    "kia ora",
    "g'day",
    "bonjour",
    "ciao",
    "hola",
    "olá",
    "namaste",
    "salaam",
    "jambo",
    "hiya",
    "howdy",
    "chale",
    "aloha",
)


DELIVERIES = {
    "formal": "[politely]",
    "warm": "[warmly]",
    "brisk": "[briskly]",
    "playful": "[playfully]",
}


def tones(character: Character) -> list[str]:
    """`TONES` in the order the character's values lean to them."""
    leaning = {
        tone: sum(character.values[value] for value in values) / len(values)
        for tone, values in LEANINGS.items()
    }
    return sorted(TONES, key=lambda tone: -leaning[tone])


def lines_for(character: Character) -> list[str]:
    """Four greetings in a new character's way of talking, from their values and speaking style."""
    first, second = tones(character)[:2]
    turn = zlib.crc32(character.id.encode())
    lines = [TONES[first][(turn + n) % len(TONES[first])] for n in range(3)]
    quoted = re.findall(r"['‘\"“]([^'’\"”]+)['’\"”]", character.speaking_style.lower())
    hello = next((word for word in quoted if word.strip(" !.,") in HELLOS), None)
    if hello:
        lines.insert(0, hello.strip(" !.,").capitalize() + "!")
    else:
        lines.append(TONES[second][turn % len(TONES[second])])
    return lines[:4]
