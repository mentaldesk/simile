from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from simile.behaviour import Activity, Goal, Need
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.engagement import initial_engagement
from simile.schema import CoreValue, Id, Relationship

PRESSING: dict[Need, str] = {
    Need.REST: "tired",
    Need.NEWS: "itching to catch up on the news",
    Need.CURIOSITY: "restless to get on with something",
}

BUSY: dict[Activity, str] = {
    Activity.NEWS: "was off to read the news",
    Activity.MAKER_SPACE: "had things to do at the maker space",
}

KEEN = ((0.75, "is keen to talk"), (0.55, "is happy to chat"), (0.4, "is lukewarm"))
WILLING = KEEN[1][0]
RELUCTANT = "would rather not talk"
LONELY, SOCIABLE = 0.7, 0.3


@dataclass(frozen=True)
class Stance:
    """How someone comes into a conversation: how keen they are, from 0 to 1, after how many
    lines they'd want to wrap it up, and what draws them in or holds them back."""

    keen: float
    leaves_after: int
    drawn: tuple[str, ...] = ()
    held: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    """The direction for a scripted conversation that `opener` starts."""

    names: dict[Id, str]
    stances: dict[Id, Stance]
    opener: Id
    leaver: Id
    length: int
    """Lines in all, goodbyes included."""

    def other(self, npc: Id) -> Id:
        return next(other for other in self.names if other != npc)


def topic_interest(
    values: Mapping[CoreValue, float], topics: Iterable[Mapping[CoreValue, float]]
) -> float:
    """From -1 to 1: how much the values the topics relate to matter to someone, weighted by how
    much each topic relates to each value. 0 without topics."""
    total = weight = 0.0
    for topic in topics:
        for value, relates in topic.items():
            total += relates * 2 * (values[value] - 0.5)
            weight += relates
    return total / weight if weight else 0.0


def stance(
    values: Mapping[CoreValue, float],
    rel: Relationship,
    goal: Goal,
    needs: Mapping[Need, float],
    topics: Iterable[Mapping[CoreValue, float]],
    other: str,
    config: ConversationConfig = DEFAULT_CONFIG,
) -> Stance:
    """How `rel.owner` comes into a conversation with `rel.about`, called `other`, while doing
    `goal`, when what's likely to come up relates to `topics`."""
    seeking = goal == Goal(Activity.SEEK, rel.about)
    pull = config.seeking_them if seeking else config.accept_goals.get(goal.activity, 0.0)
    social = needs[Need.SOCIAL]
    need, level = max(((n, needs[n]) for n in PRESSING), key=lambda item: item[1])
    keen = initial_engagement(values, rel.like, config)
    keen += config.keen_social * (social - 0.5)
    keen += config.keen_topics * topic_interest(values, topics)
    keen += config.keen_goal * pull
    keen -= config.keen_pressing * max(0.0, level - config.pressing)
    keen = min(max(keen, 0.0), 1.0)

    drawn, held = [], []
    if seeking:
        drawn.append(f"came looking for {other}")
    elif goal.activity is Activity.SEEK:
        held.append("was looking for someone else")
    elif goal.activity in BUSY:
        held.append(BUSY[goal.activity])
    if social >= LONELY:
        drawn.append("could do with company")
    elif social <= SOCIABLE:
        held.append("has had plenty of company today")
    if level > config.pressing:
        held.append(PRESSING[need])
    return Stance(round(keen, 3), leaves_after(keen, config), tuple(drawn), tuple(held))


def leaves_after(keen: float, config: ConversationConfig = DEFAULT_CONFIG) -> int:
    """Lines into a conversation someone this keen wants to wrap it up: `min_lines` at
    `leave_below` or less, `long_talk` at 1."""
    share = max(keen - config.leave_below, 0.0) / (1 - config.leave_below)
    lines = round(config.min_lines + share * (config.long_talk - config.min_lines))
    return min(max(lines, config.min_lines), config.max_lines - goodbyes(config))


def goodbyes(config: ConversationConfig = DEFAULT_CONFIG) -> int:
    return 2 if config.farewell else 1


def plan(
    names: Mapping[Id, str],
    stances: Mapping[Id, Stance],
    opener: Id,
    config: ConversationConfig = DEFAULT_CONFIG,
) -> Plan:
    """Whoever wants to wrap up first leaves, the one who was approached if it's a tie."""
    approached = next(npc for npc in names if npc != opener)
    leaver = min((approached, opener), key=lambda npc: stances[npc].leaves_after)
    length = min(stances[leaver].leaves_after + goodbyes(config), config.max_lines)
    return Plan(dict(names), dict(stances), opener, leaver, length)


def direction(plan: Plan) -> str:
    """The plan as direction for the script."""
    lines = []
    for npc, name in plan.names.items():
        stance = plan.stances[npc]
        agree, disagree = (stance.drawn, stance.held)
        if stance.keen < WILLING:
            agree, disagree = disagree, agree
        why = f" ({', '.join(agree)})" if agree else ""
        though = f", though {joined(disagree)}" if disagree else ""
        lines.append(f"- {name} {keenness(stance.keen)}{why}{though}.")
    leaver, stayer = plan.leaver, plan.other(plan.leaver)
    leaving, staying = plan.stances[leaver], plan.stances[stayer]
    names = plan.names
    if staying.leaves_after > leaving.leaves_after:
        lines.append(
            f"- {names[leaver]} will want to wrap up after about {leaving.leaves_after} lines; "
            f"{names[stayer]} would happily go on for {staying.leaves_after}."
        )
    else:
        lines.append(f"- Both will want to wrap up after about {leaving.leaves_after} lines.")
    answer = f" and {names[stayer]} answers" if plan.length > leaving.leaves_after + 1 else ""
    lines.append(
        f"- {names[plan.opener]} speaks first. About {plan.length} lines in all, ending when "
        f"{names[leaver]} takes their leave{answer}."
    )
    return "\n".join(lines)


def joined(reasons: Sequence[str]) -> str:
    return reasons[0] if len(reasons) == 1 else f"{', '.join(reasons[:-1])} and {reasons[-1]}"


def keenness(keen: float) -> str:
    return next((words for bar, words in KEEN if keen >= bar), RELUCTANT)
