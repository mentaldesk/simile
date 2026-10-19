from simile.schema import Craft, Humour, HumourStyle, Medium
from simile.works.maker import system_prompt

from .conftest import VIKTOR

VERSE = Craft(medium=Medium.WRITING, form="plain verse about old bridges")


def test_a_makers_humour_follows_how_they_talk_and_can_show_in_their_work() -> None:
    teasing = VIKTOR.model_copy(
        update={"humour": Humour(style=HumourStyle.TEASING, seriousness=0.6)}
    )

    prompt = system_prompt(teasing, VERSE)

    assert (
        f"How you talk: {VIKTOR.speaking_style}\n"
        "Your humour is teasing: gentle ribbing of people you get on with. You joke often, but "
        "never in every line. Your jokes are never cruel and never punch down, and any sarcasm "
        "stays dry, never insulting. It can show in your work too.\n\n"
        "In your own time you write plain verse"
    ) in prompt


def test_a_maker_with_no_humour_says_what_they_mean() -> None:
    none = VIKTOR.model_copy(update={"humour": Humour(style=HumourStyle.NONE, seriousness=1)})

    prompt = system_prompt(none, VERSE)

    assert "\nYou are not one for jokes: you say what you mean.\n\n" in prompt
    assert "show in your work" not in prompt


def test_without_a_humour_the_works_prompt_is_as_it_was() -> None:
    prompt = system_prompt(VIKTOR.model_copy(update={"humour": None}), VERSE)

    assert f"How you talk: {VIKTOR.speaking_style}\n\nIn your own time" in prompt
    assert "humour" not in prompt
