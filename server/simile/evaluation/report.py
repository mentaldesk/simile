from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from simile.evaluation.fake import STOCK
from simile.evaluation.metric import Spread
from simile.evaluation.play import Reply
from simile.evaluation.scenarios import NOW
from simile.schema import Character


@dataclass(frozen=True)
class Run:
    """How the replies were made, for the report's header."""

    pool: str
    sample: str
    model: str
    judge: str
    calls: int


def report(spread: Spread, replies: Sequence[Reply], run: Run) -> str:
    by = {(reply.character, reply.scenario): reply for reply in replies}
    characters = spread.characters
    lines = [
        "# Behavioural evaluation of characters",
        "",
        f"{len(characters)} characters from `{run.pool}` ({run.sample}), "
        f"{len(spread.scenarios)} scenarios. {made(run)}",
        "",
        f"**On paper:** {paper(characters)}",
        "",
        "## Spread",
        "",
        "Embedding distance is 1 minus cosine similarity, from P3's local embedding model. "
        "Evenness is the stances' entropy over the most it could be: 0 when every character "
        "does the same thing.",
        "",
        "| | Embedding distance | Stances | Evenness |",
        "|---|--:|---|--:|",
        f"| On paper: persona and backstory | {spread.persona:.2f} | | |",
        f"| On paper: core values (RMS difference) | {spread.values:.2f} | | |",
    ]
    for result in spread.scenarios:
        lines.append(
            f"| {result.scenario.title} | {result.distance:.2f} | "
            f"{tally(result.stances, list(result.scenario.stances))} | "
            f"{result.evenness:.2f} |"
        )
    lines += [
        f"| **All scenarios** | **{spread.distance:.2f}** | | **{spread.evenness:.2f}** |",
        f"| For scale: replies to different scenarios | {spread.across:.2f} | | |",
        "",
        "Short replies sit further apart than long biographies, so compare each scenario's "
        "distance with the last row, not with the paper rows. A scenario near it drew replies "
        "as different as if each character had been asked something else.",
        "",
        "Do characters further apart on paper reply further apart? Pearson r over pairs of "
        "characters, against their mean reply distance: "
        f"{r(spread.follows_values)} for core values, {r(spread.follows_persona)} for persona "
        "and backstory.",
    ]
    for result in spread.scenarios:
        scenario = result.scenario
        where = f", at {scenario.place}" if scenario.place else ""
        lines += [
            "",
            f"## {scenario.title}",
            "",
            f"{scenario.situation}",
            "",
            f'> **{scenario.name}** ({scenario.description}{where}): "{scenario.line}"',
            "",
            "| Character | Stance | Reply |",
            "|---|---|---|",
        ]
        for character in characters:
            reply = by[character.id, scenario.id]
            lines.append(
                f"| {who(character)} | {reply.stance or ''} | {cell(reply.text or reply.raw)} |"
            )
    lines += [
        "",
        f"Ages are as of {NOW:%Y-%m-%d}. Replies are as the game parses them, without the values "
        "tag, stage directions or sentences past the word limit.",
        "",
    ]
    return "\n".join(lines)


def made(run: Run) -> str:
    if run.model == STOCK:
        return (
            "Stock replies and stances stood in for Claude, so this shows only the report's shape."
        )
    return (
        f"Each reply is one call to `{run.model}` with B5's prompts (`simile.conversation`), as "
        "a world cast from these characters alone would write it at its start. "
        f"`{run.judge}` labelled the stances in one more call. Claude calls: {run.calls}."
    )


def paper(characters: Sequence[Character]) -> str:
    from simile.characters.pool import occupation_category

    genders = Counter(c.gender.value for c in characters)
    ages = [NOW.year - c.birth_year for c in characters]
    origins = {c.origin for c in characters}
    jobs = {occupation_category(c.occupation) for c in characters}
    born = sum(c.arrival is None for c in characters)
    return (
        f"{tally(genders)}; aged {min(ages)} to {max(ages)}; {len(origins)} origins; "
        f"{len(jobs)} occupation groups; {born} born in the village."
    )


def who(character: Character) -> str:
    return f"{character.name}, {NOW.year - character.birth_year}, {character.occupation}"


def tally(counts: Counter[str], order: Sequence[str] = ()) -> str:
    """Most first, then in `order`."""
    rank = {name: n for n, name in enumerate(order)}
    ranked = sorted(counts.items(), key=lambda item: (-item[1], rank.get(item[0], len(rank))))
    return ", ".join(f"{name} {n}" for name, n in ranked)


def r(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}"


def cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())
