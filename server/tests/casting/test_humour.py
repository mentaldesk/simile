from collections import Counter
from collections.abc import Callable
from datetime import date

from simile.casting import bind, cast, distance
from simile.casting.humour import humoured
from simile.schema import Character, Humour, HumourStyle

Make = Callable[..., Character]

DRY = Humour(style=HumourStyle.DRY, seriousness=0.6)


def test_a_character_without_a_humour_is_given_one(pool: list[Character]) -> None:
    [given] = humoured([pool[0].model_copy(update={"humour": None})], seed=3)

    assert given.humour is not None
    assert given.model_copy(update={"humour": None}) == pool[0].model_copy(update={"humour": None})
    assert humoured([pool[0].model_copy(update={"humour": None})], seed=3) == [given]


def test_a_characters_own_humour_is_kept(pool: list[Character]) -> None:
    mine = pool[0].model_copy(update={"humour": DRY})

    assert humoured([mine], seed=3) == [mine]


def test_styles_already_in_the_cast_are_less_likely(make: Make) -> None:
    dry = [make(f"dry_{n}", humour=DRY) for n in range(3)]
    drawn = [make(f"new_{n}") for n in range(60)]

    given = humoured([*dry, *drawn], seed=1)[3:]

    styles = Counter(c.humour.style for c in given if c.humour)
    assert styles[HumourStyle.DRY] < min(n for style, n in styles.items() if style != "dry")


def test_a_cast_of_ten_has_varied_styles(pool: list[Character]) -> None:
    for seed in range(5):
        made = bind(cast(pool, 10, seed=seed, year=2026), seed=seed, game_date=date(2026, 10, 1))
        styles = Counter(r.character.humour.style for r in made.residents if r.character.humour)

        assert sum(styles.values()) == 10
        assert len(styles) >= 6, styles
        assert max(styles.values()) <= 3, styles


def test_each_resident_gets_their_humour(pool: list[Character]) -> None:
    made = bind(pool[:2], seed=1, game_date=date(2026, 10, 1))

    assert [npc.humour for npc in made.npcs()] == [r.character.humour for r in made.residents]
    assert all(npc.humour for npc in made.npcs())


def test_different_styles_set_two_characters_further_apart(make: Make) -> None:
    a = make("a", humour=DRY)
    same = make("b", humour=DRY.model_copy(update={"seriousness": 0.2}))
    other = make("c", humour=Humour(style=HumourStyle.SILLY, seriousness=0.6))

    assert distance(a, other) > distance(a, same) == distance(make("d"), make("e"))
