from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Protocol

from simile.schema import CoreValue

if TYPE_CHECKING:
    from simile.characters.tables.load import Allowed, Conditional, Tables

OLDEST_BIRTH_YEAR = 1930
YOUNGEST_AGE = 16

type Kind = frozenset[str] | type[bool] | type[int]


class Row(Protocol):
    @property
    def id(self) -> str: ...


def problems(tables: "Tables") -> Iterator[str]:
    """Everything wrong with how the tables refer to each other, one line each."""
    yield from _names(tables)
    yield from _census(tables)
    yield from _occupations(tables)
    yield from _conditions(tables)


def skeleton_fields(tables: "Tables") -> dict[str, Kind]:
    """Census fields conditions may test: not origin or gender, so nothing is tied to them."""
    census = tables.census
    return {
        "age": int,
        "siblings": int,
        "children": int,
        "born_here": bool,
        "arrival": _ids(census.arrival),
        "background": _ids(census.background),
        "upbringing": _ids(census.upbringing),
        "education": _ids(census.education),
        "partnership": _ids(census.partnership),
        "health": _ids(census.health.condition) | {"none"},
        "work": _ids(census.work.status) | {"working"},
        "occupation_group": frozenset(group.major for group in tables.occupations.group),
    }


def score_names(tables: "Tables") -> frozenset[str]:
    domains = tables.temperament.domain
    return frozenset(
        [value.value for value in CoreValue]
        + [domain.id for domain in domains]
        + [facet.id for domain in domains for facet in domain.facet]
    )


def _names(tables: "Tables") -> Iterator[str]:
    yield from _unique("names.toml origin", (origin.id for origin in tables.origins))
    for origin in tables.origins:
        where = f"names.toml origin '{origin.id}'"
        yield from _unique(f"{where} surname", origin.surnames)
        if set(origin.women) != set(origin.men):
            yield f"{where}: women and men have different birth eras"
        for gender, eras in (("women", origin.women), ("men", origin.men)):
            if min(eras) > OLDEST_BIRTH_YEAR:
                yield f"{where}: {gender} have no names for people born in {OLDEST_BIRTH_YEAR}"
            for era, names in eras.items():
                if len(names) < 5:
                    yield f"{where}: {gender} born from {era} have fewer than 5 names"
                yield from _unique(f"{where} {gender} born from {era}", names)
        given = {
            name for eras in (origin.women, origin.men) for era in eras.values() for name in era
        }
        for name in origin.famous:
            if not any(
                name == f"{first} {family}" for first in given for family in origin.surnames
            ):
                yield f"{where}: its lists can't make the famous name '{name}' anyway"


def _census(tables: "Tables") -> Iterator[str]:
    census = tables.census
    for table in ("arrival", "background", "upbringing", "education", "partnership"):
        yield from _unique(f"census.toml {table}", (row.id for row in getattr(census, table)))
    yield from _unique("census.toml health", (row.id for row in census.health.condition))
    yield from _unique("census.toml work status", (row.id for row in census.work.status))
    by_era = [(f"background '{row.id}'", row.weight) for row in census.background]
    by_era += [(f"upbringing '{row.id}'", row.weight) for row in census.upbringing]
    by_era.append(("siblings", census.siblings))
    for where, table in by_era:
        if min(table) > OLDEST_BIRTH_YEAR:
            yield f"census.toml {where}: no weights for people born in {OLDEST_BIRTH_YEAR}"
    by_age = [(f"education '{row.id}'", row.weight) for row in census.education]
    by_age += [(f"partnership '{row.id}'", row.weight) for row in census.partnership]
    by_age += [(f"health '{row.id}'", row.weight) for row in census.health.condition]
    by_age += [(f"work status '{row.id}'", row.share) for row in census.work.status]
    by_age += [
        ("children", census.children),
        ("health share", census.health.share),
        ("work employed", census.work.employed),
    ]
    for where, table in by_age:
        if min(table) > YOUNGEST_AGE:
            yield f"census.toml {where}: no weights for {YOUNGEST_AGE}-year-olds"
    for where, table in (("siblings", census.siblings), ("children", census.children)):
        if len({len(weights) for weights in table.values()}) != 1:
            yield f"census.toml {where}: every band needs the same number of weights"
        if any(sum(weights) <= 0 for weights in table.values()):
            yield f"census.toml {where}: a band has no positive weight"
    partnerships = _ids(census.partnership)
    backgrounds = _ids(census.background)
    yield from _known("census.toml childless", census.childless, partnerships)
    for row in census.education:
        yield from _known(
            f"census.toml education '{row.id}' background", row.background, backgrounds
        )
    for row in census.background + census.upbringing + census.partnership + census.education:
        if not any(row.weight.values()):
            yield f"census.toml '{row.id}': every weight is zero"
    for upbringing in census.upbringing:
        for background in census.background:
            kinds = [k for k in upbringing.households if background.households.get(k)]
            if not kinds:
                where = f"census.toml upbringing '{upbringing.id}'"
                yield f"{where}: no household in background '{background.id}' fits it"
            for kind in set(upbringing.households) - set(background.households):
                yield f"census.toml background '{background.id}': no '{kind}' households"
    if not any(row.done_by <= YOUNGEST_AGE for row in census.education):
        yield f"census.toml education: nobody can have finished by {YOUNGEST_AGE}"


def _occupations(tables: "Tables") -> Iterator[str]:
    occupations = tables.occupations
    educations = _ids(tables.census.education)
    yield from _unique("occupations.toml group", (group.id for group in occupations.group))
    yield from _unique("occupations.toml title", (job.name for job in tables.jobs))
    if set(occupations.skill) != educations:
        yield "occupations.toml skill: needs exactly one row per education level"
    studied = {study.education for study in occupations.study}
    yield from _known("occupations.toml study", studied, educations)
    for missing in sorted(educations - studied):
        yield f"occupations.toml study: nothing to study for education '{missing}'"
    degrees = {row.id for row in tables.census.education if row.degree}
    if not degrees and any(job.degree for job in tables.jobs):
        yield "occupations.toml: titles need a degree but no education level is one"


def _conditions(tables: "Tables") -> Iterator[str]:
    fields = skeleton_fields(tables)
    scores = score_names(tables)
    events = [event.id for event in tables.events]
    tension = tables.tension
    later = [
        row.id for rows in (tension.contradiction, tension.wound, tension.secret) for row in rows
    ]
    yield from _unique(
        "events.toml and tension.toml id", events + later + [w.id for w in tension.want]
    )
    event_ids = frozenset(events)
    with_attachment = {**fields, "attachment": _ids(tables.temperament.attachment)}
    for status in tables.census.work.status:
        allowed = {
            key: kind for key, kind in fields.items() if key not in ("work", "occupation_group")
        }
        yield from _conditional(
            f"census.toml work status '{status.id}'", status, allowed, set(), set()
        )
    for event in tables.events:
        where = f"events.toml event '{event.id}'"
        yield from _conditional(where, event, fields, scores, event_ids)
        for key, spec in event.implied.items():
            yield from _spec(f"{where} implied", key, spec, fields)
        yield from _known(f"{where} after", event.after, event_ids)
        yield from _known(f"{where} not_with", event.not_with, event_ids)
        if event.id in event.after or event.id in event.not_with:
            yield f"{where}: refers to itself"
    for style in tables.temperament.attachment:
        where = f"temperament.toml attachment '{style.id}'"
        yield from _conditional(where, style, fields, scores, event_ids)
    tension_ids = event_ids | frozenset(later)
    for table in ("contradiction", "wound", "secret", "want"):
        for row in getattr(tension, table):
            where = f"tension.toml {table} '{row.id}'"
            yield from _conditional(where, row, with_attachment, scores, tension_ids)
    for table in ("wound", "secret", "want"):
        for row in getattr(tension, table):
            where = f"tension.toml {table} '{row.id}' after"
            yield from _known(where, row.after, tension_ids)
    for group in tables.mannerisms.group:
        yield from _conditional(f"mannerisms.toml group '{group.id}'", group, {}, scores, set())
    yield from _unique(
        "mannerisms.toml item", (i for g in tables.mannerisms.group for i in g.items)
    )


def _conditional(
    where: str,
    row: "Conditional",
    fields: Mapping[str, Kind],
    scores: Iterable[str],
    ids: Iterable[str],
) -> Iterator[str]:
    scores, ids = set(scores), set(ids)
    for key, spec in row.when.items():
        yield from _spec(f"{where} when", key, spec, fields)
    for key in row.lean:
        if key not in scores:
            yield f"{where}: lean on '{key}', which isn't a value, domain or facet"
    for key in row.boost:
        if "=" in key:
            field, value = key.split("=", 1)
            kind = fields.get(field)
            if kind is None:
                yield f"{where}: boost on '{field}', which isn't a field here"
            elif kind is bool and value not in ("true", "false"):
                yield f"{where}: boost '{key}' needs true or false"
            elif isinstance(kind, frozenset) and value not in kind:
                yield f"{where}: boost '{key}', but '{value}' isn't a {field}"
            elif kind is int:
                yield f"{where}: boost '{key}' can't test a number"
        elif key not in ids:
            yield f"{where}: boost on '{key}', which isn't an earlier draw or a field=value"


def _spec(where: str, key: str, spec: "Allowed", fields: Mapping[str, Kind]) -> Iterator[str]:
    from simile.characters.tables.load import Between, Except

    kind = fields.get(key)
    if kind is None:
        yield f"{where}: '{key}' isn't a field here"
    elif kind is bool:
        if not isinstance(spec, bool):
            yield f"{where}: '{key}' needs true or false"
    elif kind is int:
        if not isinstance(spec, Between):
            yield f"{where}: '{key}' needs {{min, max}}"
    elif isinstance(spec, list):
        yield from _known(f"{where} {key}", spec, kind)
    elif isinstance(spec, Except):
        yield from _known(f"{where} {key}", spec.excluded, kind)
    else:
        yield f"{where}: '{key}' needs a list of {key}s or {{not = [...]}}"


def _known(where: str, keys: Iterable[str], known: Iterable[str]) -> Iterator[str]:
    known = set(known)
    for key in keys:
        if key not in known:
            yield f"{where}: unknown '{key}'"


def _unique(where: str, items: Iterable[str]) -> Iterator[str]:
    for item, count in Counter(items).items():
        if count > 1:
            yield f"{where}: '{item}' appears {count} times"


def _ids(rows: Iterable[Row]) -> frozenset[str]:
    return frozenset(row.id for row in rows)
