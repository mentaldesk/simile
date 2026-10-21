import pytest

from simile.characters.palette import PLAYER
from simile.dolls.build import people, personas
from simile.dolls.words import described, gender_in, persona


@pytest.mark.parametrize(
    ("description", "gender"),
    [
        ("A heavy Danish accent. A woman in her late thirties.", "woman"),
        ("A heavy Ghanaian accent. A man in his early twenties.", "man"),
        ("An Indian auntie from Mumbai in her mid forties.", "woman"),
        ("A thick, broad Scots accent.", None),
    ],
)
def test_reads_a_man_or_a_woman_from_a_voice(description: str, gender: str | None) -> None:
    assert gender_in(description) == gender


def test_says_who_they_are_as_far_as_its_known() -> None:
    assert persona(27, "woman") == "A woman of 27."
    assert persona(None, "man") == "A man."
    assert persona(40, None) == "A person of 40."
    assert persona() == ""


def test_every_resident_is_a_man_or_a_woman_of_their_age() -> None:
    said = personas()

    assert said["odalys"] == "A woman of 27."
    assert set(said) == set(people()) - {"player"}
    assert all(" of " in words and "person" not in words for words in said.values())


def test_names_each_colour_precisely() -> None:
    words = described(PLAYER, "player")

    assert "golden tan skin" in words
    assert "short very dark brown hair" in words
    assert "a bright sky blue t-shirt, dark slate blue trousers and pure white sneakers" in words
    assert "backpack" in words
