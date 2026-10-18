import itertools
import random
from collections import Counter

import pytest

from simile.characters.brief import Brief
from simile.characters.generate import settle
from simile.characters.sheet import ELDER_FROM, INTERESTS, Slot, draw, plan, slots, split_name
from simile.characters.tables import YEAR, load_tables
from simile.characters.traits import RECIPES, derive_traits
from simile.characters.voice import accent_sentence, needs_recording
from simile.npc.values import TRAITS
from simile.schema import Arrival, CoreValue, Gender, HookKind

LOCKED = Brief(
    name="Danuta Sobczak",
    birth_year=1968,
    gender=Gender.WOMAN,
    origin="Poland",
    arrival=Arrival(age=34, reason="for a job"),
    occupation="Bus driver",
    values={CoreValue.HONESTY: 0.82, CoreValue.ADVENTURE: 0.08},
)


@pytest.mark.parametrize("seed", range(20))
def test_locked_fields_reach_the_sheet_unchanged(seed: int) -> None:
    sheet = draw(random.Random(seed), LOCKED)
    facts = settle(LOCKED, sheet, load_tables())

    assert {field: facts[field] for field in LOCKED.locks()} == LOCKED.locks()
    assert (sheet.skeleton.given, sheet.skeleton.family) == ("Danuta", "Sobczak")
    assert sheet.skeleton.age == YEAR - 1968
    assert (sheet.skeleton.arrived_at, sheet.skeleton.arrival) == (34, "job")
    assert sheet.values[CoreValue.HONESTY] == 0.82
    assert sheet.values[CoreValue.ADVENTURE] == 0.08
    assert all(seed.age <= sheet.skeleton.age for seed in sheet.seeds())


def test_a_locked_surname_never_makes_a_famous_name() -> None:
    brief = Brief(origin="Germany", gender=Gender.MAN, facts={"family": "Müller"})

    names = {draw(random.Random(seed), brief).skeleton.name for seed in range(400)}

    assert "Thomas Müller" not in names
    assert all(name.endswith(" Müller") for name in names)


def test_a_locked_name_picks_an_origin_with_that_name() -> None:
    sheets = [draw(random.Random(seed), Brief(name="Piotr Wójcik")) for seed in range(10)]

    assert {sheet.country for sheet in sheets} == {"Poland"}


def test_an_unknown_country_needs_a_locked_name() -> None:
    with pytest.raises(ValueError, match="no origins for country 'Atlantis'"):
        draw(random.Random(0), Brief(origin="Atlantis"))

    brief = Brief(origin="Atlantis", name="Ana Folau", arrival=Arrival(age=30, reason="for love"))
    sheet = draw(random.Random(0), brief)

    assert settle(brief, sheet, load_tables())["origin"] == "Atlantis"
    assert accent_sentence(sheet.accent) == "An accent from Atlantis."
    assert needs_recording(sheet.accent)


def test_latent_traits_steer_the_values() -> None:
    def openness(z: float) -> float:
        sheets = [draw(random.Random(s), Brief(latent={"openness": z})) for s in range(30)]
        return sum(sheet.values[CoreValue.ADVENTURE] for sheet in sheets) / len(sheets)

    assert openness(2.5) > openness(-2.5) + 0.3


def test_a_brief_rejects_unknown_traits_and_census_fields() -> None:
    with pytest.raises(ValueError, match="not latent traits: charm"):
        Brief(latent={"charm": 1.0})
    with pytest.raises(ValueError, match="not census fields: star_sign"):
        Brief(facts={"star_sign": "leo"})
    assert set(TRAITS) == {"openness", "transcendence", "outlook", "rigour"}


def test_a_plan_starts_the_same_for_any_larger_count() -> None:
    small, large = plan(3, seed=7), plan(6, seed=7)

    assert small == large[:3]
    assert len({sheet.skeleton.name for sheet in large}) == 6


@pytest.mark.parametrize("seed", range(5))
def test_a_plan_has_the_village_roles_first_then_mostly_makers_and_elders(seed: int) -> None:
    tables = load_tables()
    roles = {role.id: role for role in tables.roles}
    kinds = list(itertools.islice(slots(tables), 20))

    for sheet, slot in zip(plan(20, seed), kinds, strict=True):
        s = sheet.skeleton
        job = tables.job(s.occupation.removeprefix("retired "))
        assert job is not None
        if slot.kind == "role":
            assert slot.role is not None and roles[slot.role].fits(job)
            assert s.work == "working"
        elif slot.kind == "maker":
            assert job.maker and s.work == "working"
        else:
            assert s.age > ELDER_FROM and not job.maker and s.work in ("working", "retired")
    assert [slot.kind for slot in kinds[:8]] == ["role"] * 8
    assert [slot.role for slot in kinds[:4]] == list(roles)
    assert Counter(slot.kind for slot in kinds[8:]) == {"maker": 8, "elder": 4}


def test_a_job_that_needs_a_degree_comes_with_one_they_have_finished() -> None:
    tables = load_tables()
    for seed in range(100):
        sheet = draw(random.Random(seed), slot=Slot("maker"))
        s = sheet.skeleton
        job = tables.job(s.occupation)
        education = tables.education[s.education]
        assert job is not None and job.maker and s.work == "working"
        assert education.degree or not job.degree
        assert education.done_by <= s.age


def test_each_character_has_an_interest_worth_talking_about() -> None:
    interests = [sheet.interest for sheet in plan(20, seed=2)]

    assert set(interests) == set(INTERESTS)
    assert max(Counter(interests).values()) <= 6


def test_no_estranged_sibling_without_siblings() -> None:
    for seed in range(200):
        sheet = draw(random.Random(seed), Brief(facts={"siblings": 0}))

        assert HookKind.ESTRANGED_SIBLING not in {kind for kind, _ in sheet.hooks}
        assert 2 <= len(sheet.hooks) <= 4
        assert len({kind for kind, _ in sheet.hooks}) == len(sheet.hooks)


def test_locked_hooks_and_past_skip_their_stages() -> None:
    brief = Brief(hooks=[], past=[])
    sheet = draw(random.Random(0), brief)

    assert sheet.hooks == []
    assert sheet.events == []


@pytest.mark.parametrize(
    ("brief", "accent"),
    [
        (Brief(origin="Poland", arrival=Arrival(age=30, reason="for a job")), "Polish"),
        (Brief(origin="Poland", arrival=Arrival(age=5, reason="with family")), None),
        (Brief(origin="Poland", arrival=None), None),
        (Brief(origin="United States", arrival=Arrival(age=40, reason="for a job")), "American"),
    ],
)
def test_the_accent_is_their_origin_unless_they_grew_up_here(
    brief: Brief, accent: str | None
) -> None:
    assert draw(random.Random(0), brief).accent == accent


def test_accent_sentences() -> None:
    assert accent_sentence("Polish") == "A Polish accent."
    assert accent_sentence("English") == "An English accent."
    assert accent_sentence("Nigerian, a Yoruba speaker") == "A Nigerian accent, a Yoruba speaker."
    assert accent_sentence(None).startswith("A local accent")


def test_only_accents_voicedesign_can_do_skip_recording() -> None:
    assert needs_recording("Polish")
    assert needs_recording("English")
    assert not needs_recording("American")
    assert not needs_recording(None)


def test_split_name_keeps_surname_particles() -> None:
    assert split_name("Pieter van Wyk") == ("Pieter", "van Wyk")
    assert split_name("Miguel Ángel Hernández") == ("Miguel Ángel", "Hernández")
    assert split_name("Cher") == ("Cher", "")


def test_trait_recipes_use_real_scores() -> None:
    t = load_tables()
    facets = {facet.id for domain in t.temperament.domain for facet in domain.facet}
    known = facets | {value.value for value in CoreValue}

    assert {key for recipe in RECIPES.values() for key, _ in recipe} <= known


def test_traits_follow_temperament() -> None:
    values = {value: 0.5 for value in CoreValue}
    calm = {"forgivingness": 0.9, "gentleness": 0.9, "anxiety": 0.1, "fearfulness": 0.1}
    tense = {"forgivingness": 0.1, "gentleness": 0.1, "anxiety": 0.9, "fearfulness": 0.9}
    base = {"sociability": 0.5, "liveliness": 0.5, "prudence": 0.5, "patience": 0.5}

    forgiving, bitter = derive_traits(values, base | calm), derive_traits(values, base | tense)

    assert forgiving.forgiveness > 0.75 > 0.25 > bitter.forgiveness
    assert bitter.negativity_bias > forgiving.negativity_bias
