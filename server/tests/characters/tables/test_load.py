import re
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from simile.characters.tables import TABLES_DIR, Tables, load_tables
from simile.characters.tables.check import problems, skeleton_fields
from simile.characters.tables.load import FILES, banded

SLANG = {
    "Becky", "Bich", "Bruce", "Butt", "Can", "Chad", "Cock", "Dave", "Dick", "Dike", "Divan",
    "Dong", "Dung", "Fanny", "Ferrari", "Fick", "Garfield", "Gay", "Grażyna", "Harsh", "Ho",
    "Hore", "Hung", "Janusz", "Karen", "Kevin", "Kok", "Kunt", "Kyle", "Lamia", "Lucky", "Luigi",
    "Mario", "Marites", "Phuc", "Pratt", "Princess", "Prost", "Pula", "Purity", "Randy",
    "Schmuck", "Seaman", "Sheila", "Stacy", "Twat", "Wang", "Willy", "Wood",
}  # fmt: skip
FAMOUS = {
    ("Imran", "Khan"), ("Efren", "Reyes"), ("Romeo", "Santos"), ("Zain", "Malik"),
    ("Jieun", "Lee"), ("Chaeyoung", "Park"), ("Mario", "Rossi"), ("Larry", "King"),
    ("Luiz", "Silva"), ("Kofi", "Annan"), ("Enzo", "Ferrari"),
}  # fmt: skip


def test_every_table_loads(tables: Tables) -> None:
    assert len(tables.origins) >= 30
    assert len(tables.jobs) >= 200
    assert len(tables.events) >= 150
    assert len(tables.tension.contradiction) == 72
    assert len(tables.tension.wound) >= 30
    assert len(tables.tension.secret) >= 40
    assert len(tables.tension.want) >= 35
    assert len(tables.temperament.domain) == 6
    assert sum(len(domain.facet) for domain in tables.temperament.domain) == 24
    assert len(tables.temperament.attachment) == 4
    assert sum(len(group.items) for group in tables.mannerisms.group) >= 450
    assert list(problems(tables)) == []


@pytest.mark.parametrize("year", range(1926, 2011))
def test_every_birth_year_has_weights_and_names(tables: Tables, year: int) -> None:
    census = tables.census
    assert sum(banded(row.weight, year) for row in census.background) > 0
    assert sum(banded(row.weight, year) for row in census.upbringing) > 0
    assert sum(banded(census.siblings, year)) > 0
    for origin in tables.origins:
        for gender in ("woman", "man", "nonbinary"):
            assert origin.given_names(gender, year)


@pytest.mark.parametrize("age", range(16, 101))
def test_every_age_has_weights(tables: Tables, age: int) -> None:
    census = tables.census
    assert sum(banded(row.weight, age) for row in census.education) > 0
    assert sum(banded(row.weight, age) for row in census.partnership) > 0
    assert sum(banded(census.children, age)) > 0
    assert sum(banded(row.share, age) for row in census.work.status) > 0
    assert any(job.ages[0] <= min(age, 55) <= job.ages[1] for job in tables.jobs)


def test_occupations_are_weighted_by_eurostat_employment(tables: Tables) -> None:
    by_major: dict[str, float] = {}
    for job in tables.jobs:
        by_major[job.major] = by_major.get(job.major, 0) + job.weight
    total = sum(by_major.values())

    assert by_major["professionals"] / total == pytest.approx(0.223, abs=0.002)
    assert by_major["armed_forces"] / total == pytest.approx(0.006, abs=0.001)


def test_no_name_reads_as_slang_or_a_joke(tables: Tables) -> None:
    for origin in tables.origins:
        eras = [*origin.women.values(), *origin.men.values()]
        names = {*origin.surnames, *(name for era in eras for name in era)}
        parts = {part for name in names for part in name.split()}
        assert not parts & SLANG, origin.id


def test_no_origin_can_make_a_famous_name(tables: Tables) -> None:
    for origin in tables.origins:
        given = {name for era in [*origin.women.values(), *origin.men.values()] for name in era}
        for first, last in FAMOUS:
            assert not (first in given and last in origin.surnames), (origin.id, first, last)


def test_conditions_can_never_mention_origin_or_gender(tables: Tables) -> None:
    assert "origin" not in skeleton_fields(tables)
    assert "gender" not in skeleton_fields(tables)


def test_the_readme_gives_every_table_a_source_and_licence() -> None:
    readme = (TABLES_DIR / "README.md").read_text()

    for file, _ in FILES.values():
        assert f"`{file}`" in readme
    assert "licence" in readme.lower()


def with_event(tmp_path: Path, lines: str, id: str = "test_event") -> Path:
    directory = tmp_path / "tables"
    shutil.copytree(TABLES_DIR, directory)
    event = f'[[event]]\nid = "{id}"\ntext = "x"\nages = [20, 30]\nimpact = 10\nvalence = 0\n'
    with (directory / "events.toml").open("a") as f:
        f.write(f"\n{event}{lines}\n")
    return directory


@pytest.mark.parametrize(
    ("lines", "complaint"),
    [
        ('when = { favourite_colour = ["blue"] }', "'favourite_colour' isn't a field"),
        ('when = { origin = ["poland"] }', "'origin' isn't a field"),
        ('when = { upbringing = ["wolves"] }', "unknown 'wolves'"),
        ("when = { children = true }", "'children' needs {min, max}"),
        ("lean = { bravery = 1 }", "lean on 'bravery'"),
        ("boost = { won_the_war = 2 }", "boost on 'won_the_war'"),
        ('boost = { "education=wizardry" = 2 }', "'wizardry' isn't a education"),
        ('after = ["married_a_prince"]', "unknown 'married_a_prince'"),
        ('implied = { partnership = ["eloped"] }', "unknown 'eloped'"),
        ("lean = { honesty = 9 }", "less than or equal to 3"),
    ],
)
def test_a_condition_on_something_that_doesnt_exist_fails_to_load(
    tmp_path: Path, lines: str, complaint: str
) -> None:
    with pytest.raises(ValidationError, match=re.escape(complaint)):
        load_tables(with_event(tmp_path, lines))


def test_ids_are_unique(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="'married' appears 2 times"):
        load_tables(with_event(tmp_path, "", id="married"))


def test_a_valid_extra_event_loads(tmp_path: Path) -> None:
    lines = 'when = { education = ["degree"] }\nlean = { honesty = 1 }\nafter = ["married"]'

    assert load_tables(with_event(tmp_path, lines)).event["test_event"].after == ["married"]
