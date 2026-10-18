import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from simile.characters.brief import Brief
from simile.characters.generate import (
    TooSimilar,
    character_id,
    first_sentence,
    renamed,
    settle,
    write,
)
from simile.characters.jobs import family, job_of, retired, student
from simile.characters.novelty import Embedder, Novelty
from simile.characters.sheet import PARTICLES, plan
from simile.characters.tables import YEAR, Tables, load_tables
from simile.llm import CallRecord, LLMClient, Model, StructuredOutputError
from simile.npc.values import format_scores, ranked
from simile.schema import Character

POOL_DIR = Path(__file__).resolve().parents[3] / "content" / "characters" / "pool"
CONTENT_DIR = POOL_DIR.parents[1]
RENAMES = "renames.json"
"""Maps a renamed character's place in the plan, as `<seed>:<slot>`, to its id now, so a rerun
skips it."""
CALLS_EACH = 2
"""Claude calls a character takes when nothing has to be retried."""
HEADING = "# Character pool\n"


class NotAPool(ValueError):
    """A folder the generator mustn't write to."""


@dataclass
class Run:
    written: list[Character] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    unstarted: int = 0


async def generate_pool(
    llm: LLMClient,
    count: int,
    seed: int,
    directory: Path = POOL_DIR,
    *,
    embedder: Embedder,
    calls: Sequence[CallRecord] = (),
    max_calls: int | None = None,
    model: str = Model.HAIKU,
    retries: int = 1,
    echo: Callable[[str], None] = print,
    tables: Tables | None = None,
) -> Run:
    """Write the first `count` characters of the seed's plan that aren't in `directory` yet.
    `calls` is the client's call log, which `max_calls` caps."""
    check_writable(directory)
    t = tables or load_tables()
    directory.mkdir(parents=True, exist_ok=True)
    library = load_pool(directory)
    novelty = Novelty(embedder, library)
    renames = load_renames(directory)
    run = Run()
    try:
        for slot, sheet in enumerate(plan(count, seed, tables=t)):
            brief = Brief(values=sheet.values)
            id = character_id(settle(brief, sheet, t)["name"])
            now = renames.get(slot_key(seed, slot), id)
            if (directory / f"{now}.json").exists():
                run.skipped.append(now)
                continue
            if max_calls is not None and len(calls) + CALLS_EACH > max_calls:
                run.unstarted += 1
                continue
            try:
                result = await write(
                    llm,
                    brief,
                    sheet,
                    id=id,
                    novelty=novelty,
                    model=model,
                    retries=retries,
                    tables=t,
                )
            except (TooSimilar, StructuredOutputError) as e:
                run.failed.append(id)
                echo(f"{id}: not written. {e}")
                continue
            character = result.character
            save(character, directory)
            novelty.add(character)
            run.written.append(character)
            echo(f"{id}: {character.name}, born {character.birth_year}, {character.occupation}")
    finally:
        write_readme(directory, count, seed, tables=t)
    return run


def save(character: Character, directory: Path) -> Path:
    path = directory / f"{character.id}.json"
    path.write_text(character.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def character_files(directory: Path = POOL_DIR) -> list[Path]:
    return sorted(path for path in directory.glob("*.json") if path.name != RENAMES)


def load_pool(directory: Path = POOL_DIR) -> list[Character]:
    return [
        Character.model_validate_json(path.read_text(encoding="utf-8"))
        for path in character_files(directory)
    ]


def load_renames(directory: Path = POOL_DIR) -> dict[str, str]:
    path = directory / RENAMES
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def slot_key(seed: int, slot: int) -> str:
    return f"{seed}:{slot}"


def planned_ids(count: int, seed: int, *, tables: Tables | None = None) -> list[str]:
    """The id of the name the plan draws in each slot."""
    t = tables or load_tables()
    return [
        character_id(settle(Brief(values=sheet.values), sheet, t)["name"])
        for sheet in plan(count, seed, tables=t)
    ]


def rename(directory: Path, id: str, name: str, *, now: datetime | None = None) -> Character:
    """Give a pool character a new name and id everywhere, keeping its slot in the plan."""
    check_writable(directory)
    old = Character.model_validate_json((directory / f"{id}.json").read_text(encoding="utf-8"))
    new_id = character_id(name)
    if new_id != id and (directory / f"{new_id}.json").exists():
        raise ValueError(f"{new_id} is already in the pool")
    update = {"id": new_id, "name": name, "updated": now or datetime.now(UTC)}
    character = renamed(old.model_copy(update=update | {"version": old.version + 1}), old.name)
    save(character, directory)
    if new_id != id:
        (directory / f"{id}.json").unlink()
    if (directory / "README.md").exists():
        count, seed = readme_command(directory)
        _record(directory, seed, planned_ids(count, seed), id, new_id)
        write_readme(directory, count, seed)
    return character


def _record(directory: Path, seed: int, planned: Sequence[str], old: str, new: str) -> None:
    renames = load_renames(directory)
    for slot, drawn in enumerate(planned):
        key = slot_key(seed, slot)
        if renames.get(key, drawn) == old:
            renames.pop(key, None)
            if new != drawn:
                renames[key] = new
    text = json.dumps(renames, indent=2, sort_keys=True) + "\n"
    (directory / RENAMES).write_text(text, encoding="utf-8")


def within(path: Path, folder: Path) -> bool:
    """Whether `path` is `folder` or inside it, also on a disk that ignores case."""
    resolved, parent = (Path(str(p.resolve()).casefold()) for p in (path, folder))
    return resolved.is_relative_to(parent)


def check_writable(directory: Path) -> None:
    """Refuse anywhere in content/ but the pool, and a folder whose README.md isn't the pool's."""
    if within(directory, CONTENT_DIR) and not within(directory, POOL_DIR):
        raise NotAPool("must be outside content/ or in content/characters/pool/")
    readme = directory / "README.md"
    if readme.exists() and not readme.read_text(encoding="utf-8").startswith(HEADING):
        raise NotAPool(f"{readme} isn't a character pool's README")


def write_readme(directory: Path, count: int, seed: int, *, tables: Tables | None = None) -> Path:
    path = directory / "README.md"
    path.write_text(readme(load_pool(directory), count, seed, tables=tables), encoding="utf-8")
    return path


def readme_command(directory: Path = POOL_DIR) -> tuple[int, int]:
    """The count and seed the README says made the pool in `directory`."""
    text = (directory / "README.md").read_text(encoding="utf-8")
    if found := re.search(r"--count (\d+) --seed (\d+)", text):
        return int(found[1]), int(found[2])
    raise ValueError(f"{directory / 'README.md'} doesn't say which command made the pool")


def name_structure(name: str) -> str:
    words = name.split()
    if "-" in words[-1]:
        return "double-barrelled surname"
    if len(words) > 2 and words[-2].casefold() in PARTICLES:
        return "surname with a particle"
    if len(words) > 2:
        return "two given names"
    if "-" in words[0]:
        return "hyphenated given name"
    return "given name and surname" if len(words) == 2 else "one name"


def occupation_category(occupation: str, tables: Tables | None = None) -> str:
    """The ISCO-08 major group of their job, or what they do instead."""
    t = tables or load_tables()
    if retired(occupation):
        return "retired"
    if job := t.job(occupation):
        return job.major
    return "student" if student(occupation, t) else "not in work"


def fitting_role(occupation: str, tables: Tables | None = None) -> str | None:
    """The first of the village's roles their job fits."""
    t = tables or load_tables()
    job = job_of(occupation, t)
    if job is None or retired(occupation):
        return None
    return next((role.id for role in t.roles if role.fits(job)), None)


def age_band(birth_year: int) -> str:
    age = YEAR - birth_year
    return f"{age // 10 * 10}s" if age >= 20 else "under 20"


def readme(
    characters: Sequence[Character], count: int, seed: int, *, tables: Tables | None = None
) -> str:
    t = tables or load_tables()
    lines = [
        HEADING.strip(),
        "",
        "Premade characters for the character library (#89). Each `<id>.json` is a `Character`,",
        "generated from `server/` by",
        "",
        "```bash",
        f"uv run simile characters generate --count {count} --seed {seed}",
        "```",
        "",
        "A rerun skips the characters already here, and the first characters of a seed's plan",
        "are the same for any count, so a larger `--count` adds to the pool. Don't edit them by",
        "hand: delete one and rerun to write it again, or rename one with",
        '`uv run simile characters rename <id> "<new name>"`. `renames.json` records the',
        "seed and slot of each renamed character, so a rerun doesn't write the name the plan",
        "drew there again.",
        "",
        f"The pool has {len(characters)} characters, not the 30 #183 asks for: the user asked for",
        "a small pool. A larger one waits for #89's question on pool size.",
        "",
        "- **Jobs come first** (#235). The plan starts with two characters for each of the",
        "  village's roles (`roles.toml`), whose jobs fit it. Of the rest, 7 in 10 have a job from",
        "  `makers.toml`, people who make or think, and the others are over 60 with a trade from",
        "  `occupations.toml`, working or retired.",
        "- **Sampled in code** (`server/simile/characters/sheet.py`), from the tables in",
        "  `content/characters/tables/`: the census skeleton, values spread across the pool,",
        "  temperament, life events, a contradiction, wound, secret and want, mannerisms, the",
        "  kinds of hook, and what one of their interests is about. Nothing rare is drawn twice in",
        "  one pool, and job families and interests spread out.",
        "- **Written by Claude** (Haiku, through L1): the biography, past memories, hook",
        "  descriptions, voice and look, then a critic pass that rewrites what's generic.",
        "- **Checked in code:** a local embedding model rejects a character too close to one",
        "  already here, and traits are derived from values and temperament.",
        "- `voice.needs_recording` is true when VoiceDesign can't do the accent, so the reference",
        "  line has to be recorded and imported. `reference_clip` stays null until then.",
        "",
        "## Spread",
        "",
    ]
    spreads = {
        "Name structure": [name_structure(c.name) for c in characters],
        "Fits the role": [fitting_role(c.occupation, t) or "none" for c in characters],
        "Job family": [family(c.occupation, t) for c in characters],
        "Origin": [c.origin for c in characters],
        "Age now": [age_band(c.birth_year) for c in characters],
        "Gender": [c.gender.value for c in characters],
        "Arrival": [c.arrival.reason if c.arrival else "born here" for c in characters],
        "Voice": [
            "needs recording" if c.voice.needs_recording else "VoiceDesign" for c in characters
        ],
    }
    for title, items in spreads.items():
        lines += [f"| {title} | Characters |", "|---|--:|"]
        lines += [_row([k, str(n)]) for k, n in sorted(Counter(items).items(), key=_most)]
        lines.append("")
    lines += [
        "## Characters",
        "",
        "| Character | Born | Origin | Occupation | Cares most about | Persona |",
        "|---|--:|---|---|---|---|",
    ]
    for c in sorted(characters, key=lambda c: c.id):
        cells = [
            f"`{c.id}` {c.name}",
            str(c.birth_year),
            c.origin,
            c.occupation,
            format_scores(ranked(c.values)[:3]),
            first_sentence(c.persona),
        ]
        lines.append(_row(cells))
    return "\n".join(lines) + "\n"


def _most(item: tuple[str, int]) -> tuple[int, str]:
    return -item[1], item[0]


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"
