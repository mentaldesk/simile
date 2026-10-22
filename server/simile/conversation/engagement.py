import math
import random
from collections.abc import Iterable, Mapping

from simile.behaviour import Activity, Goal
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.schema import CoreValue, Relationship

ASPECTS = ("like", "trust", "respect")


def acceptance(
    values: Mapping[CoreValue, float],
    rel: Relationship,
    goal: Goal,
    social: float,
    config: ConversationConfig = DEFAULT_CONFIG,
    *,
    urgent: bool = False,
    unease: float = 0.0,
) -> float:
    """How keen `rel.owner` is to talk when `rel.about` walks up: positive to accept. Someone
    with an `urgent` need declines."""
    weights = config.accept_weights
    score = config.accept_base - (config.accept_urgent if urgent else 0.0)
    if unease:
        score -= config.accept_unease * unease
    score += sum(weights.get(aspect, 0.0) * (getattr(rel, aspect) - 0.5) for aspect in ASPECTS)
    score += weights.get("familiarity", 0.0) * rel.familiarity
    score += sum(w * (values[value] - 0.5) for value, w in config.accept_values.items())
    score += config.accept_social * (social - 0.5)
    if goal == Goal(Activity.SEEK, rel.about):
        return score + config.seeking_them
    return score + config.accept_goals.get(goal.activity, 0.0)


def accepts(score: float, rng: random.Random, config: ConversationConfig = DEFAULT_CONFIG) -> bool:
    if config.accept_temperature == 0:
        return score > 0
    return rng.random() < _logistic(score / config.accept_temperature)


def topic_match(values: Mapping[CoreValue, float], topics: Iterable[CoreValue]) -> float:
    """From -1 to 1: how much the values a line touches matter to someone. 0 for no topics."""
    unique = list(dict.fromkeys(topics))
    if not unique:
        return 0.0
    return sum(2 * (values[value] - 0.5) for value in unique) / len(unique)


def initial_engagement(
    values: Mapping[CoreValue, float], like: float, config: ConversationConfig = DEFAULT_CONFIG
) -> float:
    score = config.start_engagement + config.start_like * (like - 0.5)
    score += sum(w * (values[value] - 0.5) for value, w in config.start_values.items())
    return _clamp(score)


def engage(
    engagement: float,
    values: Mapping[CoreValue, float],
    like: float,
    topics: Iterable[CoreValue],
    config: ConversationConfig = DEFAULT_CONFIG,
    *,
    drain: float = 1.0,
) -> float:
    """Engagement after a line that touched `topics`, for someone who likes the other `like`,
    tiring `drain` times as fast as usual."""
    change = -config.fatigue * drain + config.topic_weight * topic_match(values, topics)
    return _clamp(engagement + change + config.like_weight * (like - 0.5))


def leaving(engagement: float, lines: int, config: ConversationConfig = DEFAULT_CONFIG) -> bool:
    """Whether someone whose turn it is after `lines` lines says goodbye now."""
    if lines >= config.max_lines - (2 if config.farewell else 1):
        return True
    return lines >= config.min_lines and engagement < config.leave_below


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-max(min(x, 50.0), -50.0)))
