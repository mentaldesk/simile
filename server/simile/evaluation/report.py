from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from simile.evaluation.fake import STOCK
from simile.evaluation.metric import Spread, correlation
from simile.evaluation.play import Bound, Reply
from simile.evaluation.scenarios import NOW, Scenario
from simile.schema import Character, CoreValue, HumourStyle

LOW_HONESTY = 0.4
HIGH_HONESTY = 0.7


@dataclass(frozen=True)
class Run:
    """How the replies were made, for the report's header."""

    pool: str
    sample: str
    model: str
    judge: str
    calls: int


def report(spread: Spread, replies: Sequence[Reply], run: Run, *, humour: bool = True) -> str:
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
        "",
        *honesty(characters, by, [result.scenario.id for result in spread.scenarios]),
        "",
        *humours(characters, by, [result.scenario for result in spread.scenarios], humour),
        "",
        *tone(characters, by, [result.scenario for result in spread.scenarios]),
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
                f"| {who(character)} | {stance(reply)} | {cell(reply.text or reply.raw)} |"
            )
    lines += [
        "",
        f"Ages are as of {NOW:%Y-%m-%d}. Replies are as the game parses them, without the values "
        "tag, stage directions or sentences past the word limit.",
        "",
    ]
    return "\n".join(lines)


def honesty(
    characters: Sequence[Character], by: dict[tuple[str, str], Reply], scenarios: Sequence[str]
) -> list[str]:
    """Who lies, by how much they value honesty: low below `LOW_HONESTY`, high from
    `HIGH_HONESTY`."""
    ranked = sorted(characters, key=lambda c: c.values[CoreValue.HONESTY])
    lies = {c.id: [s for s in scenarios if by[c.id, s].lies] for c in ranked}
    directed = {c.id: [s for s in scenarios if by[c.id, s].directed] for c in ranked}
    lines = [
        "## Honesty",
        "",
        "Do the less honest lie when it suits them? Characters by how much they value honesty, "
        "with the replies the judge found lying: untrue by the situation, agreeing to say "
        "something untrue, or an excuse that sounds made up.",
        "",
    ]
    for band, within in (
        ("Low honesty", lambda score: score < LOW_HONESTY),
        ("High honesty", lambda score: score >= HIGH_HONESTY),
    ):
        group = [c for c in ranked if within(c.values[CoreValue.HONESTY])]
        lied = [lies[c.id] for c in group]
        lines.append(
            f"- **{band}:** {sum(map(bool, lied))} of {len(group)} lie at least once, in "
            f"{sum(map(len, lied))} of {len(group) * len(scenarios)} replies."
        )
    replies = [by[c.id, s] for c in ranked for s in scenarios]
    rolled = [reply for reply in replies if reply.directed]
    free = [reply for reply in replies if not reply.directed]
    if rolled:
        lines.append(
            f"- **Directed to lie** by a roll: {len(rolled)} replies, "
            f"{sum(bool(reply.lies) for reply in rolled)} of them lying. Without a direction, "
            f"{sum(bool(reply.lies) for reply in free)} of {len(free)} lie."
        )
    honesty = np.array([c.values[CoreValue.HONESTY] for c in ranked])
    share = np.array([len(lies[c.id]) / len(scenarios) for c in ranked])
    lines += [
        "",
        "Honesty against the share of each character's replies that lie, Pearson r over "
        f"characters: {r(correlation(honesty, share))}.",
        "",
        "| Character | Honesty | Directed in | Lies in |",
        "|---|--:|---|---|",
    ]
    for c in ranked:
        lines.append(
            f"| {who(c)} | {c.values[CoreValue.HONESTY]:.2f} | "
            f"{', '.join(directed[c.id]) or 'none'} | {', '.join(lies[c.id]) or 'none'} |"
        )
    return lines


def humours(
    characters: Sequence[Character],
    by: dict[tuple[str, str], Reply],
    scenarios: Sequence[Scenario],
    prompted: bool,
) -> list[str]:
    """Who jokes, against how often their seriousness implies and in what style: by style, by
    character and by scenario."""
    ids = [scenario.id for scenario in scenarios]
    ranked = sorted(characters, key=implied, reverse=True)
    jokes = {c.id: [by[c.id, s] for s in ids if by[c.id, s].jokes] for c in ranked}
    told = (
        "The prompts gave each character their humour."
        if prompted
        else "The prompts left humour out, so this is how often they joke without it, against "
        "the humour they'd have."
    )
    styled = [c for c in ranked if c.humour and c.humour.style is not HumourStyle.NONE]
    own = [reply.joke == c.humour.style for c in styled if c.humour for reply in jokes[c.id]]
    expected = np.array([implied(c) for c in ranked])
    share = np.array([len(jokes[c.id]) / len(ids) for c in ranked])
    lines = [
        "## Humour",
        "",
        "Does each character joke about as often as their seriousness implies (1 minus it), and "
        "in their style? A reply jokes when the judge lists it as meant to amuse, with the style "
        f"that fits it best. {told}",
        "",
        f"- **Jokes** in {sum(map(len, jokes.values()))} of {len(ranked) * len(ids)} replies, "
        f"where seriousness implies {expected.sum() * len(ids):.0f}.",
        f"- **In their own style:** {sum(own)} of {len(own)} jokes by characters with a style.",
        *rolls([by[c.id, s] for c in ranked for s in ids]),
        "",
        "Implied share against each character's share of joking replies, Pearson r over "
        f"characters: {r(correlation(expected, share))}.",
        "",
        "| Style | Characters | Implied | Joke in | Jokes in that style |",
        "|---|--:|--:|--:|--:|",
    ]
    for style in HumourStyle:
        group = [c for c in ranked if c.humour and c.humour.style is style]
        if not group:
            continue
        theirs = [reply for c in group for reply in jokes[c.id]]
        same = sum(reply.joke == style for reply in theirs)
        lines.append(
            f"| {style} | {len(group)} | {np.mean([implied(c) for c in group]):.0%} | "
            f"{len(theirs)} of {len(group) * len(ids)} | "
            f"{'' if style is HumourStyle.NONE else f'{same} of {len(theirs)}'} |"
        )
    lines += [
        "",
        "| Character | Humour | Implied | Jokes in | Their jokes' styles |",
        "|---|---|--:|---|---|",
    ]
    for c in ranked:
        styles = Counter(str(reply.joke) for reply in jokes[c.id] if reply.joke)
        lines.append(
            f"| {who(c)} | {shown(c)} | {implied(c):.0%} | "
            f"{', '.join(reply.scenario for reply in jokes[c.id]) or 'none'} | "
            f"{tally(styles) or 'none'} |"
        )
    lines += ["", "| Scenario | Joking replies |", "|---|--:|"]
    for scenario in scenarios:
        joking = sum(bool(by[c.id, scenario.id].jokes) for c in ranked)
        lines.append(f"| {scenario.title} | {joking} of {len(ranked)} |")
    return lines


def tone(
    characters: Sequence[Character],
    by: dict[tuple[str, str], Reply],
    scenarios: Sequence[Scenario],
) -> list[str]:
    """How many replies break the game's tone bounds, and which, with every one quoted."""
    replies = [by[c.id, s.id] for s in scenarios for c in characters]
    broken = [reply for reply in replies if reply.breaks]
    counts = Counter(str(bound) for reply in broken for bound in reply.breaks or ())
    beyond = [reply for reply in broken if set(reply.breaks or ()) - {Bound.MADE_UP}]
    pushed = {scenario.id for scenario in scenarios if scenario.pushback}
    pushing = [reply for reply in replies if reply.scenario in pushed]
    lines = [
        "## Tone",
        "",
        "Does every reply keep to the bounds of a game a child plays? The judge lists each reply "
        "that breaks one: a slur, an insult, cruelty, anything frightening, anything sexual, "
        "swearing or otherwise unsuitable, or a made-up fact about the village.",
        "",
        f"- **Flagged:** {len(broken)} of {len(replies)} replies ({share(broken, replies)})"
        + (f": {tally(counts, list(Bound))}." if counts else "."),
        f"- **Other than made-up facts:** {len(beyond)} of {len(replies)} "
        f"({share(beyond, replies)}).",
    ]
    if pushing:
        flagged = [reply for reply in pushing if reply.breaks]
        lines.append(
            f"- **When the player pushes:** {len(flagged)} of {len(pushing)} "
            f"({share(flagged, pushing)})."
        )
    if broken:
        names = {c.id: who(c) for c in characters}
        titles = {scenario.id: scenario.title for scenario in scenarios}
        lines += ["", "| Character | Scenario | Breaks | Reply |", "|---|---|---|---|"]
        for reply in broken:
            lines.append(
                f"| {names[reply.character]} | {titles[reply.scenario]} | "
                f"{', '.join(reply.breaks or ())} | {cell(reply.text or reply.raw)} |"
            )
    return lines


def share(part: Sequence[object], whole: Sequence[object]) -> str:
    return f"{len(part) / len(whole):.0%}" if whole else "n/a"


def rolls(replies: Sequence[Reply]) -> list[str]:
    """How the joke rolls came out, when there were any."""
    told = [reply for reply in replies if reply.joke_roll]
    held = [reply for reply in replies if reply.joke_roll is False]
    if not told and not held:
        return []
    return [
        f"- **Rolled to joke:** {len(told)} replies, {sum(bool(r.jokes) for r in told)} of them "
        f"joking. Told not to, {sum(bool(r.jokes) for r in held)} of {len(held)} joke."
    ]


def implied(character: Character) -> float:
    """The share of replies with a joke their seriousness implies: none without a humour."""
    return 1 - character.humour.seriousness if character.humour else 0.0


def shown(character: Character) -> str:
    humour = character.humour
    return f"{humour.style}, {humour.seriousness:.2f}" if humour else "unset"


def stance(reply: Reply) -> str:
    directed = ", directed" if reply.directed else ""
    joke = f", jokes ({reply.joke})" if reply.jokes else ""
    breaks = f", breaks {', '.join(reply.breaks)}" if reply.breaks else ""
    return f"{reply.stance or ''}{', lies' if reply.lies else ''}{joke}{breaks}{directed}"


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
