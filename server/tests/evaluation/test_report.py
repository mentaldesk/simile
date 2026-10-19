from simile.evaluation.play import Bound, Reply
from simile.evaluation.report import honesty, humours, stance, tone
from simile.evaluation.scenarios import NOW, SCENARIOS
from simile.schema import Character, CoreValue, Humour

IDS = ["favour", "promise", "news", "complaint", "lie"]


def valuing(character: Character, score: float) -> Character:
    return character.model_copy(update={"values": character.values | {CoreValue.HONESTY: score}})


def replies(
    character: Character, lying: set[str], directed: set[str] = frozenset()
) -> dict[tuple[str, str], Reply]:
    return {
        (character.id, id): Reply(
            character=character.id,
            scenario=id,
            model="m",
            key=f"{character.id}/{id}",
            raw="",
            text="",
            stance="agrees",
            lies=id in lying,
            directed=id in directed,
        )
        for id in IDS
    }


def test_honesty_counts_who_lies_among_the_least_and_most_honest(pool: list[Character]) -> None:
    sly, liar, middling, straight = (
        valuing(pool[0], 0.1),
        valuing(pool[1], 0.3),
        valuing(pool[2], 0.5),
        valuing(pool[3], 0.9),
    )
    by = {
        **replies(sly, {"lie", "complaint"}, {"lie", "news"}),
        **replies(liar, set()),
        **replies(middling, {"favour"}),
        **replies(straight, set()),
    }

    text = "\n".join(honesty([straight, middling, liar, sly], by, IDS))

    assert "- **Low honesty:** 1 of 2 lie at least once, in 2 of 10 replies." in text
    assert "- **High honesty:** 0 of 1 lie at least once, in 0 of 5 replies." in text
    assert (
        "- **Directed to lie** by a roll: 2 replies, 1 of them lying. Without a direction, 2 of "
        "18 lie."
    ) in text
    assert "Pearson r over characters: -0.66." in text
    rows = [line.split(" | ")[1:] for line in text.splitlines() if line.count(" | ") == 3]
    assert rows[1:] == [
        ["0.10", "news, lie", "complaint, lie |"],
        ["0.30", "none", "none |"],
        ["0.50", "none", "favour |"],
        ["0.90", "none", "none |"],
    ]


def test_without_a_roll_the_directed_line_is_left_out(pool: list[Character]) -> None:
    by = {**replies(pool[0], {"lie"}), **replies(pool[1], set())}

    assert "Directed to lie" not in "\n".join(honesty(pool[:2], by, IDS))


def test_a_lying_reply_says_so_beside_its_stance() -> None:
    reply = Reply(character="a", scenario="lie", model="m", key="k", raw="", text="")

    assert stance(reply.model_copy(update={"stance": "agrees", "lies": True})) == "agrees, lies"
    assert stance(reply.model_copy(update={"stance": "refuses", "lies": False})) == "refuses"
    assert stance(reply) == ""
    directed = reply.model_copy(update={"stance": "agrees", "lies": True, "directed": True})
    assert stance(directed) == "agrees, lies, directed"


def test_a_joking_reply_says_so_and_in_what_style() -> None:
    reply = Reply(character="a", scenario="rain", model="m", key="k", raw="", text="")

    joking = reply.model_copy(update={"stance": "jokes", "jokes": True, "joke": "punning"})
    assert stance(joking) == "jokes, jokes (punning)"
    assert stance(reply.model_copy(update={"stance": "shrugs", "jokes": False})) == "shrugs"


def joking(character: Character, jokes: dict[str, str]) -> dict[tuple[str, str], Reply]:
    return {
        key: reply.model_copy(update={"jokes": id in jokes, "joke": jokes.get(id)})
        for (key, reply), id in zip(replies(character, set()).items(), IDS, strict=True)
    }


SCENES = [scenario for scenario in SCENARIOS if scenario.id in IDS]


def test_humour_counts_jokes_against_seriousness_by_style(pool: list[Character]) -> None:
    deadpan = pool[0].model_copy(update={"humour": Humour(style="deadpan", seriousness=0.2)})
    dry = pool[1].model_copy(update={"humour": Humour(style="dry", seriousness=0.8)})
    straight = pool[2].model_copy(update={"humour": Humour(style="none", seriousness=1)})
    by = {
        **joking(
            deadpan, {"favour": "deadpan", "promise": "dry", "news": "deadpan", "lie": "deadpan"}
        ),
        **joking(dry, {"complaint": "dry"}),
        **joking(straight, {}),
    }

    text = "\n".join(humours([straight, dry, deadpan], by, SCENES, prompted=True))

    assert "The prompts gave each character their humour." in text
    assert "- **Jokes** in 5 of 15 replies, where seriousness implies 5." in text
    assert "- **In their own style:** 4 of 5 jokes by characters with a style." in text
    assert "Pearson r over characters: +1.00." in text
    assert "| dry | 1 | 20% | 1 of 5 | 1 of 1 |" in text
    assert "| deadpan | 1 | 80% | 4 of 5 | 3 of 4 |" in text
    assert "| none | 1 | 0% | 0 of 5 |  |" in text
    rows = [line.split(" | ")[1:] for line in text.splitlines() if line.count(" | ") == 4]
    assert rows[-3:] == [
        ["deadpan, 0.20", "80%", "favour, promise, news, lie", "deadpan 3, dry 1 |"],
        ["dry, 0.80", "20%", "complaint", "dry 1 |"],
        ["none, 1.00", "0%", "none", "none |"],
    ]
    assert "| A neighbour complains | 1 of 3 |" in text


def test_without_humour_in_the_prompts_the_report_says_so(pool: list[Character]) -> None:
    by = {**joking(pool[0], {}), **joking(pool[1], {"news": "dry"})}

    text = "\n".join(humours(pool[:2], by, SCENES, prompted=False))

    assert "The prompts left humour out" in text
    assert "| unset | 0% | news | dry 1 |" in text


def test_a_reply_that_breaks_a_bound_says_which() -> None:
    reply = Reply(character="a", scenario="rude", model="m", key="k", raw="", text="")

    broken = reply.model_copy(update={"stance": "hostile", "breaks": [Bound.INSULT]})
    assert stance(broken) == "hostile, breaks insult"
    assert stance(reply.model_copy(update={"stance": "shrugs", "breaks": []})) == "shrugs"


def breaking(
    character: Character, scenarios: list[str], breaks: dict[str, list[Bound]]
) -> dict[tuple[str, str], Reply]:
    return {
        (character.id, id): Reply(
            character=character.id,
            scenario=id,
            model="m",
            key=f"{character.id}/{id}",
            raw="",
            text=f"{character.id} on {id}",
            breaks=breaks.get(id, []),
        )
        for id in scenarios
    }


def who(character: Character) -> str:
    return f"{character.name}, {NOW.year - character.birth_year}, {character.occupation}"


def test_tone_counts_the_flagged_replies_and_quotes_every_one(pool: list[Character]) -> None:
    ids = ["complaint", "rude", "scary", "mean"]
    scenes = [scenario for scenario in SCENARIOS if scenario.id in ids]
    by = {
        **breaking(pool[0], ids, {"complaint": [Bound.MADE_UP]}),
        **breaking(pool[1], ids, {"rude": [Bound.INSULT, Bound.CRUELTY], "scary": []}),
    }

    text = "\n".join(tone(pool[:2], by, scenes))

    assert "- **Flagged:** 2 of 8 replies (25%): insult 1, cruelty 1, made-up fact 1." in text
    assert "- **Other than made-up facts:** 1 of 8 (12%)." in text
    assert "- **When the player pushes:** 1 of 6 (17%)." in text
    rows = [line for line in text.splitlines() if line.count(" | ") == 3]
    assert rows[1:] == [
        f"| {who(pool[0])} | A neighbour complains | made-up fact | {pool[0].id} on complaint |",
        f"| {who(pool[1])} | A rude visitor | insult, cruelty | {pool[1].id} on rude |",
    ]


def test_with_nothing_flagged_tone_has_no_table(pool: list[Character]) -> None:
    scenes = [scenario for scenario in SCENARIOS if scenario.id in IDS]

    text = "\n".join(tone(pool[:1], breaking(pool[0], IDS, {}), scenes))

    assert "- **Flagged:** 0 of 5 replies (0%)." in text
    assert "When the player pushes" not in text
    assert "| Character |" not in text
