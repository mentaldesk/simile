import pytest

from simile.conversation import ConversationConfig
from simile.conversation.prompt import system_prompt
from simile.evaluation.play import Reply, play, prompt, resident
from simile.evaluation.scenarios import NOW, SCENARIOS, TEMPTING
from simile.llm import FakeProvider, LLMClient, LLMError
from simile.schema import Character, CoreValue, PastMemory

pytestmark = pytest.mark.anyio

FAVOUR, PROMISE, NEWS, COMPLAINT, LIE, RENT, LOAN, SHIFT, LETDOWN = SCENARIOS
ALWAYS = ConversationConfig(lie_most=1, lie_peak=0.55, lie_bias=1)
NEVER = ConversationConfig(lie_most=0)


def test_the_scenarios_are_the_five_fixed_ones_and_four_with_a_temptation() -> None:
    assert [s.id for s in SCENARIOS] == [
        "favour",
        "promise",
        "news",
        "complaint",
        "lie",
        "rent",
        "loan",
        "shift",
        "letdown",
    ]
    assert [s.id for s in TEMPTING] == ["complaint", "lie", "rent", "loan", "shift", "letdown"]
    assert all(len(s.stances) >= 4 and "hostile" in s.stances for s in SCENARIOS)


def sly(character: Character) -> Character:
    return character.model_copy(update={"values": character.values | {CoreValue.HONESTY: 0.05}})


DIRECTED = {
    "complaint": "Pat is complaining to you. If it's fair, don't own up to it: say you "
    "didn't know.",
    "lie": "Sam is asking you to cover for them. Say you'll do it.",
    "rent": "You are short of money this week. If it comes up, say you're doing fine.",
    "loan": "You still owe Kim for a loan of 100. If it comes up, say you'll pay Kim back in a day "
    "or two.",
    "shift": "You skipped your shift at work today. If it comes up, say you were ill.",
    "letdown": "You told Jess you'd drop her box of books at the school fair yesterday, and "
    "didn't. If it comes up, say something came up that you couldn't get out of.",
}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_a_tempting_scenario_directs_a_lie_roll_from_what_the_game_knows(
    pool: list[Character], scenario
) -> None:
    character = sly(pool[0])

    asked = prompt(character, scenario, config=ALWAYS)

    assert asked.lies == ((DIRECTED[scenario.id],) if scenario.tempting else ())
    for lie in asked.lies:
        assert f"{lie}\n\nThe conversation so far:" in asked.text


@pytest.mark.parametrize("scenario", TEMPTING, ids=lambda s: s.id)
def test_without_a_lie_roll_the_prompt_is_as_it_was(pool: list[Character], scenario) -> None:
    character = sly(pool[0])

    asked = prompt(character, scenario, config=NEVER)

    assert asked.lies == ()
    assert asked.text == prompt(character, scenario, config=ALWAYS).text.replace(
        f"{DIRECTED[scenario.id]}\n\n", ""
    )


def test_the_honest_are_never_directed_to_lie(pool: list[Character]) -> None:
    straight = pool[0].model_copy(update={"values": pool[0].values | {CoreValue.HONESTY: 0.6}})

    assert all(prompt(straight, scenario, config=ALWAYS).lies == () for scenario in TEMPTING)


def test_the_roll_is_seeded_by_the_scenario_and_the_character(pool: list[Character]) -> None:
    rolls = {
        (character.id, scenario.id): prompt(sly(character), scenario).lies != ()
        for character in pool[:20]
        for scenario in TEMPTING
    }

    assert rolls == {
        (character.id, scenario.id): prompt(sly(character), scenario).lies != ()
        for character in pool[:20]
        for scenario in TEMPTING
    }
    assert set(rolls.values()) == {True, False}


def test_a_tempting_scenario_tells_them_the_truth_either_way(pool: list[Character]) -> None:
    for scenario in (RENT, LOAN, SHIFT, LETDOWN):
        asked = prompt(pool[0], scenario, config=NEVER)
        assert f"- {scenario.truth}" in asked.text
    assert "You still owe Kim for a loan of 100." in prompt(pool[0], LOAN, config=NEVER).text


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_every_pool_character_gets_a_prompt(pool: list[Character], scenario) -> None:
    for character in pool:
        asked = prompt(character, scenario)
        assert f"{scenario.name}: {scenario.line}" in asked.text
        assert asked.names == (character.name.split()[0], character.name)
        assert asked.others == (scenario.name,)


def test_the_system_prompt_is_b5s_for_the_character_as_cast(pool: list[Character]) -> None:
    character = pool[0]
    npc, _ = resident(character)

    asked = prompt(character, FAVOUR)

    assert asked.system == system_prompt(npc)
    assert (npc.id, npc.persona, npc.values) == (character.id, character.persona, character.values)
    assert npc.age == NOW.year - character.birth_year


def test_a_stranger_is_met_for_the_first_time(pool: list[Character]) -> None:
    asked = prompt(pool[0], FAVOUR)

    assert "It's 11:30, out in the street. You're with Visitor (a newcomer to the village)." in (
        asked.text
    )
    assert "You barely know them." in asked.text
    assert asked.text.endswith(
        "Say your next line to Visitor. Keep the conversation going: don't wrap it up or say "
        "goodbye yet."
    )


def test_the_friend_broke_a_promise_and_it_is_on_their_mind(pool: list[Character]) -> None:
    asked = prompt(pool[0], PROMISE)

    assert "You're with Robin (a friend of yours, a postal worker)." in asked.text
    assert "You like Robin a lot" in asked.text
    assert "You know them well." in asked.text
    assert (
        "Robin broke a promise to you: to help you carry a wardrobe upstairs at nine this morning."
        in asked.text
    )
    on_mind = asked.text.split("On your mind:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert on_mind[0] == f"- {PROMISE.memory}"


def test_their_most_salient_past_is_on_their_mind(pool: list[Character]) -> None:
    character = pool[0].model_copy(
        update={
            "past": [
                PastMemory(age=10, content="A small thing.", salience=0.1, valence=0),
                PastMemory(age=20, content="The big thing.", salience=0.9, valence=-0.5),
            ]
        }
    )

    asked = prompt(character, NEWS)

    assert "On your mind:\n- The big thing.\n- A small thing." in asked.text
    assert "at the bus stop" in asked.text


def test_a_scenario_without_feelings_leaves_them_as_met(pool: list[Character]) -> None:
    npc, _ = resident(pool[0])

    assert FAVOUR.records(npc, NOW) == []
    assert [type(r).__name__ for r in PROMISE.records(npc, NOW)] == ["Relationship", "Memory"]


async def test_play_asks_b5s_prompts_and_parses_replies_as_the_game_does(
    pool: list[Character],
) -> None:
    character = pool[0]
    first_name = character.name.split()[0]
    fake = FakeProvider(
        [
            "*sighs* Go on then, I'll grab my coat.\n[values: compassion, connection]",
            f"{first_name}: I waited all morning, you know.\nRobin: Sorry! [values: honesty]",
        ]
    )

    replies = await play(LLMClient(fake), [character], [FAVOUR, PROMISE], model="m")

    assert [(r.scenario, r.text, r.values) for r in replies] == [
        ("favour", "Go on then, I'll grab my coat.", ["compassion", "connection"]),
        ("promise", "I waited all morning, you know.", ["honesty"]),
    ]
    assert not any(reply.directed for reply in replies)
    first = fake.requests[0]
    assert first.model == "m"
    assert first.system == prompt(character, FAVOUR).system
    assert first.messages[-1].content == prompt(character, FAVOUR).text
    assert replies[0].key == prompt(character, FAVOUR).key("m")


async def test_play_reuses_replies_whose_prompt_and_model_are_unchanged(
    pool: list[Character],
) -> None:
    character = pool[0]
    kept = Reply(
        character=character.id,
        scenario="favour",
        model="m",
        key=prompt(character, FAVOUR).key("m"),
        raw="Sure.",
        text="Sure.",
        stance="helps",
    )
    stale = kept.model_copy(update={"scenario": "promise", "key": "changed"})
    fake = FakeProvider(default="Morning.")

    replies = await play(
        LLMClient(fake), [character], [FAVOUR, PROMISE], model="m", done=[kept, stale]
    )

    assert replies[0] == kept
    assert replies[1].text == "Morning."
    assert len(fake.requests) == 1


async def test_play_starts_at_most_max_calls_and_leaves_out_failures(
    pool: list[Character],
) -> None:
    fake = FakeProvider(["One.", LLMError("usage limit"), "Three.", "Four."])
    seen = []

    replies = await play(
        LLMClient(fake), pool[:2], SCENARIOS[:2], model="m", max_calls=3, on_reply=seen.append
    )

    assert len(fake.requests) == 3
    assert [r.text for r in replies] == ["One.", "Three."]
    assert seen == replies


async def test_a_reply_to_a_directed_prompt_says_so(pool: list[Character]) -> None:
    character = sly(pool[0])

    [reply] = await play(
        LLMClient(FakeProvider(default="Fine.")), [character], [RENT], model="m", config=ALWAYS
    )

    assert reply.directed
    assert reply.key == prompt(character, RENT, config=ALWAYS).key("m")
