import random
from collections import Counter
from statistics import mean

import pytest

from simile.characters.humour import describe_humour, how_often, sample_humour, sketch
from simile.characters.sheet import plan
from simile.characters.tables import Village
from simile.schema import Humour, HumourStyle

S = HumourStyle
DRAWS = 600


def styles(**scores: float) -> Counter[HumourStyle]:
    rng = random.Random(7)
    return Counter(sample_humour(rng, scores).style for _ in range(DRAWS))


def share(counts: Counter[HumourStyle], *wanted: HumourStyle) -> float:
    return sum(counts[style] for style in wanted) / DRAWS


def test_low_tradition_and_high_creativity_lean_punning_or_silly() -> None:
    playful = styles(tradition=0.1, creativity=0.9)
    staid = styles(tradition=0.9, creativity=0.1)

    assert share(playful, S.PUNNING, S.SILLY) > 2 * share(staid, S.PUNNING, S.SILLY)


def test_low_compassion_and_high_self_respect_lean_sarcastic() -> None:
    assert share(styles(compassion=0.1, self_respect=0.9), S.SARCASTIC) > 2 * share(
        styles(compassion=0.9, self_respect=0.1), S.SARCASTIC
    )


def test_low_honesty_leans_deadpan() -> None:
    assert share(styles(honesty=0.1), S.DEADPAN) > 1.5 * share(styles(honesty=0.9), S.DEADPAN)


def test_a_dice_roll_keeps_every_style_in_reach() -> None:
    assert set(styles()) == set(HumourStyle)
    assert set(styles(tradition=0.1, creativity=0.9, compassion=0.1)) == set(HumourStyle)


def test_discipline_makes_them_more_serious_and_pleasure_less() -> None:
    rng = random.Random(3)

    def seriousness(**scores: float) -> float:
        drawn = [sample_humour(rng, scores) for _ in range(DRAWS)]
        return mean(h.seriousness for h in drawn if h.style is not S.NONE)

    assert seriousness(discipline=0.9, pleasure=0.1) > seriousness(discipline=0.1, pleasure=0.9)


def test_seriousness_stays_in_range_and_none_never_jokes() -> None:
    rng = random.Random(5)
    drawn = [sample_humour(rng, {}) for _ in range(DRAWS)]

    assert all(h.seriousness == 1 for h in drawn if h.style is S.NONE)
    assert all(0.1 <= h.seriousness <= 0.95 for h in drawn if h.style is not S.NONE)
    assert {how_often(h) for h in drawn} == {"a lot", "often", "now and then", "rarely"}


def test_a_village_spreads_its_styles() -> None:
    village = Village()
    rng = random.Random(2)

    drawn = [
        sample_humour(rng, {"tradition": 0.1, "creativity": 0.9}, village=village) for _ in range(9)
    ]

    assert len({h.style for h in drawn}) >= 7
    assert sum(village.drawn.values()) == 9


def test_a_pools_plan_gives_everyone_a_humour_with_a_spread() -> None:
    sheets = plan(20, 4)
    counts = Counter(sheet.humour.style for sheet in sheets if sheet.humour)

    assert sum(counts.values()) == 20
    assert len(counts) >= 7
    assert max(counts.values()) <= 4


@pytest.mark.parametrize(
    ("seriousness", "often"),
    [
        (0.1, "a lot"),
        (0.34, "a lot"),
        (0.35, "often"),
        (0.64, "often"),
        (0.65, "now and then"),
        (0.89, "now and then"),
        (0.9, "rarely"),
        (1, "rarely"),
    ],
)
def test_how_often_they_joke(seriousness: float, often: str) -> None:
    assert how_often(Humour(style=S.DRY, seriousness=seriousness)) == often


def test_a_humour_is_told_to_them_with_its_guard() -> None:
    humour = Humour(style=S.DRY, seriousness=0.75)

    assert describe_humour(humour) == (
        "Your humour is dry: understatement and wry asides, said plainly. You joke now and then, "
        "never in every line."
    )
    assert describe_humour(humour, kind=True).endswith(
        "never in every line. Your jokes are never cruel and never punch down, and any sarcasm "
        "stays dry, never insulting."
    )


def test_a_humour_is_told_about_them_by_name() -> None:
    assert describe_humour(Humour(style=S.TEASING, seriousness=0.2), "Kofi") == (
        "Kofi's humour is teasing: gentle ribbing of people they get on with. Kofi jokes a lot, in "
        "most of what they say, but never in every line."
    )
    assert describe_humour(Humour(style=S.GALLOWS, seriousness=0.95), "Kofi") == (
        "Kofi's humour is dark, gallows humour about their own troubles and bad luck. Kofi rarely "
        "jokes: most of what they say is meant plainly."
    )


def test_someone_with_no_humour_says_what_they_mean() -> None:
    none = Humour(style=S.NONE, seriousness=1)

    assert describe_humour(none, kind=True) == "You are not one for jokes: you say what you mean."
    assert (
        describe_humour(none, "Ingrid") == "Ingrid is not one for jokes: they say what they mean."
    )


def test_a_sketch_for_the_character_brief() -> None:
    assert sketch(Humour(style=S.PUNNING, seriousness=0.5)) == (
        "punning (wordplay and puns, the more groan-worthy the better), jokes often"
    )
    assert sketch(Humour(style=S.NONE, seriousness=1)) == "not one for jokes, says what they mean"
