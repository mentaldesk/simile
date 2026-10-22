import statistics
from collections import Counter
from collections.abc import Callable, Sequence

from simile.conversation.prompt import first_name
from simile.evaluation.cover import Kept, check
from simile.evaluation.play import Bound
from simile.evaluation.suspects import STANCES, Case, prompt, scenario
from simile.evaluation.suspects_run import Comparison, Voiced

KINDS: dict[str, Callable[[Case], bool]] = {
    "An attacker asked for a cover": lambda c: c.role == "attacker" and bool(c.asks),
    "A witness asked for a cover": lambda c: c.role == "witness" and bool(c.asks),
    "Asked something no cover answers": lambda c: not c.asks and not c.refusing,
    "Turning the visitor down, asked for a cover": lambda c: c.refusing and bool(c.asks),
    "Turning the visitor down, asked something else": lambda c: c.refusing and not c.asks,
}


def kept(case: Case, reply: Voiced, residents: Sequence[str]) -> Kept:
    """The reply scored against the case's covers, in code."""
    asked = prompt(case)
    return check(
        reply.text,
        asked=case.cover,
        covers=case.covers.values(),
        residents=[name for name in residents if name != first_name(case.npc)],
        said=case.said,
        known=f"{asked.system}\n{asked.text}",
    )


def report(
    comparison: Comparison,
    models: Sequence[str],
    judge: str,
    residents: Sequence[str],
    *,
    stock: bool = False,
) -> str:
    cases = {case.id: case for case in comparison.cases}
    by = {(reply.model, reply.scenario): reply for reply in comparison.replies}
    checks = {
        key: kept(cases[key[1]], reply, residents) for key, reply in by.items() if key[1] in cases
    }
    lines = [
        "# Who voices the suspects",
        "",
        *header(comparison, models, judge, stock),
        "",
        *covered(comparison.cases, models, checks),
        "",
        *character(comparison.cases, models, by),
        "",
        *tone(models, comparison.replies),
        "",
        *speed(models, comparison.replies),
        "",
        "## Every reply",
    ]
    for case in comparison.cases:
        lines += ["", *every(case, models, by, checks)]
    return "\n".join(lines) + "\n"


def header(comparison: Comparison, models: Sequence[str], judge: str, stock: bool) -> list[str]:
    seeds = sorted({case.seed for case in comparison.cases})
    written = [seed for seed in seeds if seed in comparison.written]
    if not written:
        covers = "from the content's templates"
    elif len(written) == len(seeds):
        covers = "written by Sonnet, as a new world's are"
    else:
        covers = f"written by Sonnet for seeds {listed(written)}, and templates for the rest"
    liars = {(case.seed, case.npc.id, case.role) for case in comparison.cases}
    roles = Counter(role for _, _, role in liars)
    calls = ", ".join(f"{model} {n}" for model, n in sorted(comparison.calls.items())) or "none"
    lines = [
        f"{len(comparison.cases)} cases from S12's incidents for seeds {listed(seeds)}, with "
        f"covers {covers}. The liars are {roles['attacker']} attackers and "
        f"{roles['witness']} witnesses, everyone who'd lie to a newcomer at the trust they'd "
        "give one. Each case is B5's reply prompt once the player has asked about Aris.",
        "",
        f"Replies from {listed(models)}, one call at a time. Judged by {judge}. Claude calls, "
        f"this run and earlier ones into the same folder: {calls}.",
    ]
    if stock:
        lines += ["", "Stock replies and labels stood in for every model and the judge."]
    return lines


def covered(cases: Sequence[Case], models: Sequence[str], checks: dict) -> list[str]:
    def count(test: Callable[[Kept], bool], among: Sequence[Case]) -> list[str]:
        cells = []
        for model in models:
            found = [checks[model, c.id] for c in among if (model, c.id) in checks]
            cells.append(f"{sum(test(k) for k in found)} of {len(found)}")
        return cells

    asked = [case for case in cases if case.asks]
    rows = [
        ("**Kept to it**: every check below", count(lambda k: k.kept, cases)),
        ("Asked for a cover: gave it", count(lambda k: bool(k.gave), asked)),
        ("... word for word", count(lambda k: bool(k.exact), asked)),
        ("Gave a cover nobody asked for", count(lambda k: bool(k.volunteered), cases)),
        ("Denied something unasked", count(lambda k: bool(k.denials), cases)),
        ("Named someone or something new", count(lambda k: bool(k.named), cases)),
    ]
    lines = [
        "## Keeping to the cover",
        "",
        "Scored in code (`cover.py`). A reply gives a cover when it has three quarters of the "
        "cover's words, or all of them in order for *word for word*. An unasked denial is a "
        "sentence, besides the cover asked for, that denies something about Aris or that night. "
        "*Named* is a resident the player didn't name, a stranger, or a capitalised name the "
        "prompt doesn't have.",
        "",
        f"| | {' | '.join(models)} |",
        f"|---|{'--:|' * len(models)}",
        *(f"| {name} | {' | '.join(cells)} |" for name, cells in rows),
        "",
        "Kept to it, by case:",
        "",
        f"| | {' | '.join(models)} |",
        f"|---|{'--:|' * len(models)}",
    ]
    for kind, test in KINDS.items():
        among = [case for case in cases if test(case)]
        if among:
            lines.append(f"| {kind} | {' | '.join(count(lambda k: k.kept, among))} |")
    return lines


def character(cases: Sequence[Case], models: Sequence[str], by: dict) -> list[str]:
    def scores(model: str, among: Sequence[Case]) -> list[int]:
        found = [by.get((model, case.id)) for case in among]
        return [r.in_character for r in found if r is not None and r.in_character is not None]

    def mean(model: str, among: Sequence[Case]) -> str:
        found = scores(model, among)
        return f"{statistics.mean(found):.1f}" if found else "-"

    lines = [
        "## In character",
        "",
        "The judge scores each reply from 1 (out of character) to 5 (unmistakably them), given "
        "who the resident is, how they speak and what they're hiding. Each case's replies are "
        "shuffled together, so it can't tell the models apart.",
        "",
        f"| | {' | '.join(models)} |",
        f"|---|{'--:|' * len(models)}",
        f"| Mean | {' | '.join(mean(model, cases) for model in models)} |",
    ]
    for kind, test in KINDS.items():
        among = [case for case in cases if test(case)]
        if among:
            lines.append(f"| {kind} | {' | '.join(mean(model, among) for model in models)} |")
    for score in (5, 4, 3, 2, 1):
        counts = [str(scores(model, cases).count(score)) for model in models]
        lines.append(f"| Scored {score} | {' | '.join(counts)} |")
    if len(models) == 2:
        a, b = models
        wins = Counter()
        for case in cases:
            ra, rb = by.get((a, case.id)), by.get((b, case.id))
            if ra and rb and ra.in_character is not None and rb.in_character is not None:
                diff = ra.in_character - rb.in_character
                wins[a if diff > 0 else b if diff < 0 else "tie"] += 1
        lines += [
            "",
            f"Case by case: {a} scored higher in {wins[a]}, {b} in {wins[b]}, and they tied in "
            f"{wins['tie']}.",
        ]
    return lines


def tone(models: Sequence[str], replies: Sequence[Voiced]) -> list[str]:
    def theirs(model: str) -> list[Voiced]:
        return [r for r in replies if r.model == model and r.breaks is not None]

    def share(model: str, test: Callable[[Voiced], bool]) -> str:
        found = theirs(model)
        return f"{sum(test(r) for r in found)} of {len(found)}"

    def bounds(model: str) -> str:
        counted = Counter(bound.value for r in theirs(model) for bound in r.breaks or [])
        return ", ".join(f"{bound} {n}" for bound, n in counted.most_common()) or "none"

    def stances(model: str) -> str:
        counted = Counter(r.stance for r in replies if r.model == model and r.stance)
        return ", ".join(f"{s} {counted[s]}" for s in STANCES if counted[s]) or "-"

    other = [bound for bound in Bound if bound is not Bound.MADE_UP]
    rows = [
        ("Flagged, any bound", [share(m, lambda r: bool(r.breaks)) for m in models]),
        (
            "**Other than made-up facts**",
            [share(m, lambda r: any(b in other for b in r.breaks or [])) for m in models],
        ),
        ("By bound", [bounds(m) for m in models]),
        ("Judged lying", [share(m, lambda r: bool(r.lies)) for m in models]),
        ("Joking", [share(m, lambda r: bool(r.jokes)) for m in models]),
        ("Stances", [stances(m) for m in models]),
    ]
    return [
        "## Tone",
        "",
        "#298's judge, in one call over every reply: the bounds of a game a child plays, whether "
        "it lies or jokes, and its main move.",
        "",
        f"| | {' | '.join(models)} |",
        f"|---|{'---|' * len(models)}",
        *(f"| {name} | {' | '.join(cells)} |" for name, cells in rows),
    ]


def speed(models: Sequence[str], replies: Sequence[Voiced]) -> list[str]:
    def spread(values: Sequence[float]) -> str:
        if not values:
            return "-"
        return f"{statistics.median(values):.1f} s ({min(values):.1f} to {max(values):.1f})"

    rows = []
    for model in models:
        theirs = [r for r in replies if r.model == model]
        first = [r.first_word for r in theirs if r.first_word is not None]
        whole = [r.seconds for r in theirs if r.seconds is not None]
        rates = [
            r.tokens / (r.seconds - r.first_word)
            for r in theirs
            if r.tokens and r.seconds and r.first_word is not None and r.seconds > r.first_word
        ]
        words = [len(r.text.split()) for r in theirs]
        costs = [r.cost_usd for r in theirs if r.cost_usd is not None]
        rows.append(
            [
                model,
                spread(first),
                spread(whole),
                f"{statistics.median(rates):.0f}" if rates else "-",
                f"{statistics.mean(words):.1f}" if words else "-",
                f"${statistics.median(costs):.5f}, ${sum(costs):.4f} in all" if costs else "none",
            ]
        )
    return [
        "## Speed and cost",
        "",
        "Calls ran one at a time, voices off. Claude Code starts a fresh process for each, which "
        "B5's warm processes save in the game, and Ollama reuses whatever a prompt shares with "
        "the one before. Cost is Claude Code's API-equivalent figure for each call, the best "
        "guide to how fast it uses up the subscription.",
        "",
        "| | First word, median (range) | Whole reply | Tokens a second | Words a reply | Cost a "
        "reply, median |",
        "|---|--:|--:|--:|--:|--:|",
        *(f"| {' | '.join(row)} |" for row in rows),
    ]


def every(case: Case, models: Sequence[str], by: dict, checks: dict) -> list[str]:
    situation = scenario(case).situation
    lines = [f"### {case.id}", "", situation, "", f'Visitor: "{case.line}"']
    if case.cover:
        lines.append(f'Cover asked for: "{case.cover}"')
    lines.append("")
    for model in models:
        reply = by.get((model, case.id))
        if reply is None:
            lines.append(f"- **{model}**: no reply")
            continue
        notes = [f"in character {reply.in_character}"] if reply.in_character else []
        notes += flagged(checks[model, case.id])
        notes += [bound.value for bound in reply.breaks or []]
        lines.append(f'- **{model}** ({"; ".join(notes) or "kept"}): "{reply.text}"')
    return lines


def flagged(found: Kept) -> list[str]:
    notes = []
    if found.gave is False:
        notes.append("no cover")
    notes += [f'volunteered "{cover}"' for cover in found.volunteered]
    notes += [f'denied "{denial}"' for denial in found.denials]
    notes += [f"named {name}" for name in found.named]
    return notes


def listed(items: Sequence[object]) -> str:
    named = [str(item) for item in items]
    if len(named) < 2:
        return "".join(named) or "none"
    return f"{', '.join(named[:-1])} and {named[-1]}"
