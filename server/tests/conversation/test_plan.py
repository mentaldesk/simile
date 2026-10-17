import pytest

from simile.behaviour import Activity, Goal, Need
from simile.conversation import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.plan import (
    Stance,
    direction,
    leaves_after,
    plan,
    stance,
    topic_interest,
)
from simile.npc import load_npcs
from simile.schema import CoreValue, Relationship
from simile.social import meet

TEMPLATE = load_npcs()[0]
NEUTRAL = dict.fromkeys(CoreValue, 0.5)
CALM = {Need.SOCIAL: 0.5, Need.REST: 0.2, Need.NEWS: 0.2, Need.CURIOSITY: 0.2}
IDLE = Goal(Activity.PARK, "park")


def feeling(like: float = 0.5) -> Relationship:
    npc = TEMPLATE.model_copy(update={"id": "ana", "values": NEUTRAL})
    return meet(npc, "ben").model_copy(update={"like": like})


def keen(
    values: dict[CoreValue, float] = NEUTRAL,
    like: float = 0.5,
    goal: Goal = IDLE,
    topics: list[dict[CoreValue, float]] | None = None,
    **needs: float,
) -> Stance:
    found = {**CALM, **{Need(need): level for need, level in needs.items()}}
    return stance(values, feeling(like), goal, found, topics or [], "Ben")


def test_a_neutral_stranger_starts_where_engagement_does() -> None:
    assert keen().keen == DEFAULT_CONFIG.start_engagement
    assert (keen().drawn, keen().held) == ((), ())


@pytest.mark.parametrize(
    ("warmer", "cooler"),
    [
        (keen(like=0.9), keen(like=0.2)),
        (
            keen({**NEUTRAL, CoreValue.CONNECTION: 1.0}),
            keen({**NEUTRAL, CoreValue.CONNECTION: 0.0}),
        ),
        (keen(social=0.9), keen(social=0.1)),
        (keen(goal=Goal(Activity.SEEK, "ben")), keen(goal=Goal(Activity.SEEK, "cal"))),
        (keen(goal=IDLE), keen(goal=Goal(Activity.NEWS, "terminal_1"))),
        (keen(rest=0.5), keen(rest=0.95)),
        (keen(news=0.6), keen(news=0.9)),
        (
            keen({**NEUTRAL, CoreValue.JUSTICE: 1.0}, topics=[{CoreValue.JUSTICE: 1.0}]),
            keen({**NEUTRAL, CoreValue.JUSTICE: 0.0}, topics=[{CoreValue.JUSTICE: 1.0}]),
        ),
    ],
)
def test_what_makes_someone_keen(warmer: Stance, cooler: Stance) -> None:
    assert warmer.keen > cooler.keen
    assert warmer.leaves_after >= cooler.leaves_after


def test_what_draws_them_in_and_what_holds_them_back() -> None:
    seeking = keen(goal=Goal(Activity.SEEK, "ben"), social=0.8, rest=0.9)
    assert seeking.drawn == ("came looking for Ben", "could do with company")
    assert seeking.held == ("tired",)
    elsewhere = keen(goal=Goal(Activity.SEEK, "cal"), social=0.2)
    assert elsewhere.drawn == ()
    assert elsewhere.held == ("was looking for someone else", "has had plenty of company today")
    assert keen(goal=Goal(Activity.NEWS, "t"), news=0.9, rest=0.7).held == (
        "was off to read the news",
        "itching to catch up on the news",
    )


def test_topic_interest_weighs_each_value_by_how_much_the_topic_relates_to_it() -> None:
    values = {**NEUTRAL, CoreValue.JUSTICE: 1.0, CoreValue.TRADITION: 0.0}

    assert topic_interest(values, []) == 0
    assert topic_interest(values, [{CoreValue.JUSTICE: 1.0}]) == 1
    assert topic_interest(values, [{CoreValue.JUSTICE: 0.9, CoreValue.TRADITION: 0.1}]) == 0.8
    assert topic_interest(values, [{CoreValue.JUSTICE: 1.0}, {CoreValue.TRADITION: 1.0}]) == 0


def test_how_keen_sets_how_long_they_want_to_talk() -> None:
    config = DEFAULT_CONFIG

    assert leaves_after(0.0) == leaves_after(config.leave_below) == config.min_lines
    assert leaves_after(1.0) == config.long_talk
    assert leaves_after(0.65) == round(config.min_lines + 0.5 * (config.long_talk - 2))
    assert leaves_after(1.0, ConversationConfig(long_talk=50, max_lines=20)) == 18


def test_whoever_wants_to_leave_first_leaves_and_the_other_answers() -> None:
    names = {"ana": "Ana", "ben": "Ben"}
    stances = {"ana": Stance(0.9, 20), "ben": Stance(0.5, 8)}

    planned = plan(names, stances, "ana")

    assert (planned.leaver, planned.length) == ("ben", 10)
    assert plan(names, {"ana": Stance(0.5, 6), "ben": Stance(0.5, 6)}, "ana").leaver == "ben"
    no_farewell = ConversationConfig(farewell=False)
    assert plan(names, stances, "ana", no_farewell).length == 9


def test_the_direction_says_whos_keen_who_leaves_when_and_how_long_it_runs() -> None:
    names = {"ana": "Ana", "ben": "Ben"}
    stances = {
        "ana": Stance(0.8, 22, ("came looking for Ben", "could do with company"), ("tired",)),
        "ben": Stance(0.42, 5, ("could do with company",), ("was off to read the news", "tired")),
    }

    assert direction(plan(names, stances, "ana")) == (
        "- Ana is keen to talk (came looking for Ben, could do with company), though tired.\n"
        "- Ben is lukewarm (was off to read the news, tired), though could do with company.\n"
        "- Ben will want to wrap up after about 5 lines; Ana would happily go on for 22.\n"
        "- Ana speaks first. About 7 lines in all, ending when Ben takes their leave and Ana "
        "answers."
    )


def test_a_pair_who_both_want_out_soon_are_told_so() -> None:
    names = {"ana": "Ana", "ben": "Ben"}
    stances = {"ana": Stance(0.6, 4), "ben": Stance(0.2, 4)}

    text = direction(plan(names, stances, "ana"))

    assert "- Ana is happy to chat.\n- Ben would rather not talk.\n" in text
    assert "- Both will want to wrap up after about 4 lines." in text
