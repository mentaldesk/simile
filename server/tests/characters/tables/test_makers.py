import re
import shutil
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from simile.characters.tables import TABLES_DIR, Tables, load_tables

FAMILIES = {
    "science", "biology", "medicine", "bionics", "earth", "ecology", "robotics", "writing", "art",
    "music", "building", "planning", "philosophy", "founders", "games",
}  # fmt: skip


def test_the_makers_table_loads_with_every_family(tables: Tables) -> None:
    jobs = tables.maker_jobs
    by_family = Counter(job.group for job in jobs)

    assert {family.id for family in tables.makers.families} == FAMILIES
    assert set(by_family) == FAMILIES
    assert min(by_family.values()) >= 5
    assert all(job.maker and job.makes for job in jobs)
    assert sum(job.weight for job in jobs) == pytest.approx(len(FAMILIES))
    assert tables.job("Board game designer") == next(
        j for j in jobs if j.name == "board game designer"
    )


def test_a_job_takes_its_familys_ages_and_degree_unless_it_says_otherwise(tables: Tables) -> None:
    philosopher = tables.job("philosopher of mind")
    choreographer = tables.job("robot choreographer for stage shows")

    assert philosopher is not None and choreographer is not None
    assert (philosopher.ages, philosopher.degree, philosopher.major) == (
        (24, 90),
        True,
        "professionals",
    )
    assert (choreographer.ages, choreographer.degree) == ((21, 60), False)


def test_some_occupations_make_things_too(tables: Tables) -> None:
    makes = {job.name for job in tables.jobs if job.makes}

    assert {"carpenter", "architect", "journalist", "musician", "games programmer"} <= makes
    assert not {"court clerk", "barista", "payroll officer", "hairdresser"} & makes


def test_every_role_has_jobs_that_fit_it(tables: Tables) -> None:
    fitting = {role.id: {job.name for job in tables.role_jobs(role)} for role in tables.roles}

    assert list(fitting) == ["barista", "cook", "maker_space_host", "gallery_host"]
    assert fitting["barista"] == {"barista"}
    assert fitting["cook"] == {"cook", "chef"}
    assert "programmer of drone swarms" in fitting["maker_space_host"]
    assert "typeface designer" in fitting["gallery_host"]
    assert all(role.shifts for role in tables.roles)


def with_line(tmp_path: Path, file: str, after: str, line: str) -> Path:
    directory = tmp_path / "tables"
    shutil.copytree(TABLES_DIR, directory)
    path = directory / file
    text = path.read_text(encoding="utf-8")
    assert after in text
    path.write_text(text.replace(after, f"{after}{line}\n", 1), encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("line", "complaint"),
    [
        ('  { title = "dream cartographer", family = "dreams" },', "unknown family 'dreams'"),
        ('  { family = "science" },', "title"),
        ('  { title = "", family = "science" },', "at least 1 character"),
        ('  { title = "comet herder", family = "science", age = [20, 60] },', "Extra inputs"),
        ('  { title = "comet herder", family = "science", ages = [60, 20] },', "60 is after 20"),
        ('  { title = "comet herder", family = "science", degree = "maybe" },', "valid boolean"),
        ('  { title = "Logician", family = "philosophy" },', "'logician' appears 2 times"),
        ('  { title = "Barista", family = "art" },', "'barista' appears 2 times"),
    ],
)
def test_a_bad_maker_line_is_refused(tmp_path: Path, line: str, complaint: str) -> None:
    directory = with_line(tmp_path, "makers.toml", "jobs = [\n", line)

    with pytest.raises(ValidationError, match=re.escape(complaint)):
        load_tables(directory)


def test_a_good_maker_line_loads(tmp_path: Path) -> None:
    line = '  { title = "comet herder", family = "science", ages = [30, 60] },'

    tables = load_tables(with_line(tmp_path, "makers.toml", "jobs = [\n", line))

    job = tables.job("comet herder")
    assert job is not None and (job.group, job.ages, job.degree) == ("science", (30, 60), True)


@pytest.mark.parametrize(
    ("old", "new", "complaint"),
    [
        ('jobs = ["barista"]', 'jobs = ["barista", "lion tamer"]', "no job 'lion tamer'"),
        ('jobs = ["barista"]', 'families = ["dreams"]', "unknown 'dreams'"),
        ('workplace = "noodle_bar"', 'workplace = "coffee_shop"', "'coffee_shop' appears 2 times"),
        (
            'pay = { kind = "takings" }',
            'pay = { kind = "wage" }',
            "a wage needs an amount per hour",
        ),
        ("start = 7, end = 17", "start = 17, end = 7", "doesn't end after it starts"),
    ],
)
def test_a_bad_role_is_refused(tmp_path: Path, old: str, new: str, complaint: str) -> None:
    directory = tmp_path / "tables"
    shutil.copytree(TABLES_DIR, directory)
    path = directory / "roles.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

    with pytest.raises(ValidationError, match=re.escape(complaint)):
        load_tables(directory)
