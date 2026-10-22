"""Recorded greetings, which the client plays as a resident starts talking to the player."""

import hashlib
import json
import re
import zlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field, TypeAdapter

from simile.schema import Character, CoreValue, Id, Model, Npc, Voice

if TYPE_CHECKING:
    from simile.library import Library

REPO_ROOT = Path(__file__).resolve().parents[3]
GREETINGS = REPO_ROOT / "content" / "voices" / "greetings"
LINES = GREETINGS / "lines.json"
MADE = GREETINGS / "made.json"
SYNTHESIS = 1
"""Bump it when a change to `speak.py` changes how greetings come out, so they're made again."""
SUFFIX = ".m4a"


class Greeting(Model):
    text: str = Field(min_length=1, max_length=40)
    take: int = Field(default=0, ge=0, description="Another take of the same words, if one's off.")


class Made(Model):
    digest: str = Field(description="The `digest` of the voice and lines they were made from.")
    seconds: list[float]


_lines = TypeAdapter(dict[Id, list[Greeting]])
_made = TypeAdapter(dict[Id, Made])


def load_lines(path: Path | None = None) -> dict[Id, list[Greeting]]:
    return _lines.validate_json((path or LINES).read_bytes())


def load_made(path: Path | None = None) -> dict[Id, Made]:
    path = path or MADE
    return _made.validate_json(path.read_bytes()) if path.exists() else {}


def save_made(made: Mapping[Id, Made], path: Path | None = None) -> None:
    dumped = {id: made[id].model_dump() for id in sorted(made)}
    (path or MADE).write_text(json.dumps(dumped, indent=2) + "\n", encoding="utf-8")


def digest(voice: Voice, lines: Iterable[Greeting]) -> str:
    """Changes whenever the voice's clip or transcript, a line or `SYNTHESIS` does."""
    if voice.reference_clip is None:
        raise ValueError("the voice has no reference clip")
    said = json.dumps([line.model_dump() for line in lines])
    head = f"greetings {SYNTHESIS}\n{voice.reference_line}\n{said}\n".encode()
    return hashlib.sha256(head + (REPO_ROOT / voice.reference_clip).read_bytes()).hexdigest()


def outdated(
    npcs: Iterable[Npc], lines: Mapping[Id, list[Greeting]], made: Mapping[Id, Made]
) -> list[Npc]:
    """The voiced residents with lines whose greetings are missing or were made from others."""
    return [
        npc
        for npc in npcs
        if npc.voice.reference_clip is not None
        and npc.id in lines
        and (npc.id not in made or made[npc.id].digest != digest(npc.voice, lines[npc.id]))
    ]


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


def lines_for(character: Character) -> list[str]:
    """Four greetings in a new character's way of talking, from their values and speaking style."""
    leaning = {
        tone: sum(character.values[value] for value in values) / len(values)
        for tone, values in LEANINGS.items()
    }
    first, second = sorted(TONES, key=lambda tone: -leaning[tone])[:2]
    turn = zlib.crc32(character.id.encode())
    lines = [TONES[first][(turn + n) % len(TONES[first])] for n in range(3)]
    quoted = re.findall(r"['‘\"“]([^'’\"”]+)['’\"”]", character.speaking_style.lower())
    hello = next((word for word in quoted if word.strip(" !.,") in HELLOS), None)
    if hello:
        lines.insert(0, hello.strip(" !.,").capitalize() + "!")
    else:
        lines.append(TONES[second][turn % len(TONES[second])])
    return lines[:4]
