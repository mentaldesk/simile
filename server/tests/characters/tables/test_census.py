import random
from collections import Counter
from collections.abc import Callable

import pytest

from simile.characters.tables import YEAR, Skeleton, Tables, Village, jobs_for, sample_skeleton

type Skeletons = Callable[..., Skeleton]


def test_a_seed_gives_the_same_skeleton(skeleton: Skeletons) -> None:
    assert skeleton(40, seed=3) == skeleton(40, seed=3)
    assert skeleton(40, seed=3) != skeleton(40, seed=4)


@pytest.mark.parametrize("gender", ["woman", "man"])
def test_a_name_comes_from_their_origin_gender_and_birth_era(
    tables: Tables, skeleton: Skeletons, gender: str
) -> None:
    for seed in range(200):
        s = skeleton(random.Random(seed).randint(18, 90), seed=seed, gender=gender)
        origin = tables.origin[s.origin]

        assert s.birth_year == YEAR - s.age
        assert s.given in origin.given_names(gender, s.birth_year)
        assert s.family in origin.surnames
        assert s.name == f"{s.given} {s.family}"


def test_older_people_get_older_names(tables: Tables, skeleton: Skeletons) -> None:
    england = tables.origin["england"]
    old = {skeleton(85, seed=i, origin="england", gender="woman").given for i in range(30)}
    young = {skeleton(25, seed=i, origin="england", gender="woman").given for i in range(30)}

    assert old <= set(england.women[1930])
    assert young <= set(england.women[1990])


def test_another_gender_draws_from_every_name(tables: Tables, skeleton: Skeletons) -> None:
    korea = tables.origin["south_korea"]
    names = {
        skeleton(30, seed=i, origin="south_korea", gender="nonbinary").given for i in range(80)
    }

    assert names & set(korea.women[1990]) and names & set(korea.men[1990])


@pytest.mark.parametrize("seed", range(20))
def test_a_village_uses_no_name_part_or_job_twice(seed: int) -> None:
    rng, village = random.Random(seed), Village()
    cast = [sample_skeleton(rng, rng.randint(18, 90), village=village) for _ in range(12)]

    parts = [part for s in cast for part in (s.given, s.family)]
    jobs = [s.occupation.removeprefix("retired ") for s in cast if s.occupation_group]
    assert len(parts) == len(set(parts))
    assert len(jobs) == len(set(jobs))
    assert village.names == set(parts)


def test_few_older_people_work_and_only_in_jobs_open_to_their_age(
    tables: Tables, skeleton: Skeletons
) -> None:
    jobs = {job.name: job for job in tables.jobs}
    work = Counter()
    for seed in range(600):
        s = skeleton(75, seed=seed)
        work[s.work] += 1
        if s.work == "working":
            assert jobs[s.occupation].ages[1] >= 75

    assert work["working"] < 0.05 * 600
    assert work["retired"] > 0.8 * 600
    assert all(skeleton(88, seed=seed).work != "working" for seed in range(200))


def test_retired_people_are_retired_from_a_real_job(tables: Tables, skeleton: Skeletons) -> None:
    names = {job.name for job in tables.jobs}
    retired = [s for s in (skeleton(80, seed=i) for i in range(100)) if s.work == "retired"]

    assert retired
    for s in retired:
        assert s.occupation.removeprefix("retired ") in names
        assert s.occupation_group is not None


def test_jobs_respect_age_and_degree(tables: Tables) -> None:
    jobs = {job.name: job for job in tables.jobs}
    rng = random.Random(1)
    for _ in range(500):
        s = sample_skeleton(rng, rng.randint(18, 70))
        if s.work == "working":
            job = jobs[s.occupation]
            assert job.ages[0] <= s.age <= job.ages[1]
            assert not job.degree or tables.education[s.education].degree
            assert s.occupation_group == job.major


def test_education_shifts_the_kind_of_job(skeleton: Skeletons) -> None:
    def majors(education: str) -> Counter:
        people = (skeleton(40, seed=i, education=education, work="working") for i in range(300))
        return Counter(s.occupation_group for s in people)

    graduates, early = majors("postgraduate"), majors("early_leaver")

    assert graduates["professionals"] > 3 * early["professionals"]
    assert early["elementary"] > 3 * graduates["elementary"]


def test_jobs_for_lists_only_open_jobs(tables: Tables) -> None:
    for job, weight in jobs_for(tables, 70, "early_leaver"):
        assert job.ages[0] <= 70 <= job.ages[1] and not job.degree and weight > 0


def test_anyone_still_studying_is_a_student(tables: Tables, skeleton: Skeletons) -> None:
    for seed in range(20):
        s = skeleton(19, seed=seed, education="degree")
        [study] = [study for study in tables.occupations.study if study.education == "degree"]

        assert s.work == "student"
        assert s.occupation in study.titles
        assert s.occupation_group is None


def test_statuses_follow_the_rest_of_the_skeleton(skeleton: Skeletons) -> None:
    people = [skeleton(40, seed=i, children=0, health="none") for i in range(2000)]
    statuses = Counter(s.work for s in people)

    assert statuses["working"] and statuses["unemployed"]
    assert not statuses["home"] and not statuses["sick"]


def test_where_they_came_from_fits_their_age(tables: Tables) -> None:
    arrivals = {arrival.id: arrival for arrival in tables.census.arrival}
    rng = random.Random(2)
    people = [sample_skeleton(rng, rng.randint(18, 90)) for _ in range(500)]

    assert any(s.born_here for s in people) and not all(s.born_here for s in people)
    for s in people:
        if s.born_here:
            assert s.arrival is None and s.arrived_at is None
        else:
            arrival = arrivals[s.arrival]
            assert arrival.ages[0] <= s.arrived_at <= min(arrival.ages[1], s.age)


def test_fixed_fields_are_kept_and_the_rest_follow_them(skeleton: Skeletons) -> None:
    s = skeleton(34, seed=5, origin="ghana", gender="woman", partnership="widowed", children=2)

    assert (s.origin, s.gender, s.partnership, s.children) == ("ghana", "woman", "widowed", 2)
    potter = skeleton(60, seed=1, occupation="potter")
    assert (potter.work, potter.occupation_group) == ("working", "craft")
    assert skeleton(70, seed=1, occupation="retired potter").work == "retired"
    assert skeleton(30, seed=1, occupation="lion tamer").occupation_group is None


def test_an_unknown_fixed_field_is_an_error(skeleton: Skeletons) -> None:
    with pytest.raises(TypeError, match="star_sign"):
        skeleton(30, star_sign="leo")
