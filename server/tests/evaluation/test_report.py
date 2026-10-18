from simile.evaluation.play import Reply
from simile.evaluation.report import honesty, stance
from simile.evaluation.scenarios import SCENARIOS
from simile.schema import Character, CoreValue

IDS = [scenario.id for scenario in SCENARIOS]


def valuing(character: Character, score: float) -> Character:
    return character.model_copy(update={"values": character.values | {CoreValue.HONESTY: score}})


def replies(character: Character, lying: set[str]) -> dict[tuple[str, str], Reply]:
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
        **replies(sly, {"lie", "complaint"}),
        **replies(liar, set()),
        **replies(middling, {"favour"}),
        **replies(straight, set()),
    }

    text = "\n".join(honesty([straight, middling, liar, sly], by, IDS))

    assert "- **Low honesty:** 1 of 2 lie at least once, in 2 of 10 replies." in text
    assert "- **High honesty:** 0 of 1 lie at least once, in 0 of 5 replies." in text
    rows = [line.split(" | ")[1:] for line in text.splitlines() if line.count(" | ") == 2]
    assert rows[1:] == [
        ["0.10", "complaint, lie |"],
        ["0.30", "none |"],
        ["0.50", "favour |"],
        ["0.90", "none |"],
    ]


def test_a_lying_reply_says_so_beside_its_stance() -> None:
    reply = Reply(character="a", scenario="lie", model="m", key="k", raw="", text="")

    assert stance(reply.model_copy(update={"stance": "agrees", "lies": True})) == "agrees, lies"
    assert stance(reply.model_copy(update={"stance": "refuses", "lies": False})) == "refuses"
    assert stance(reply) == ""
