import re

from simile.news.config import DEFAULT_CONFIG, NewsConfig
from simile.schema import CoreValue, NewsItem, Npc

WORD = re.compile(r"[a-z]+")
COMMON = frozenset(
    {"about", "from", "into", "other", "rather", "than", "that", "their", "them", "they", "this"}
    | {"things", "with"}
)


def words(text: str) -> set[str]:
    """The words of `text` that could name a topic, without a plural ending."""
    found = (word for word in WORD.findall(text.lower()) if word not in COMMON)
    return {word.removesuffix("s") for word in found if len(word) >= 4}


def pulls(npc: Npc, item: NewsItem) -> list[float]:
    """How strongly each of the NPC's values draws them to the article, strongest first: how
    much more than most they care about it (`2 * value - 1`, or 0) times how related the article
    is to it, whichever side it takes."""
    return sorted(
        (max(2 * npc.values[value] - 1, 0.0) * item.values[value] for value in CoreValue),
        reverse=True,
    )


def alignment(npc: Npc, item: NewsItem, config: NewsConfig = DEFAULT_CONFIG) -> float:
    """The article's pulls on the NPC, each counting `config.value_decay` times less than the
    one before, so its strongest link to what they care about counts most."""
    return sum(pull * config.value_decay**-rank for rank, pull in enumerate(pulls(npc, item)))


def matching_tags(npc: Npc, item: NewsItem) -> list[str]:
    """The article's tags that share a word with the NPC's interests."""
    theirs = words(" ".join(npc.interests))
    return [tag for tag in item.tags if words(tag) & theirs]


def interest(npc: Npc, item: NewsItem, config: NewsConfig = DEFAULT_CONFIG) -> float:
    """How much `npc` wants to read the analysed `item`: how it bears on what they value most,
    whether it touches their interests, and a little for a tone that suits their optimism."""
    optimism = 2 * npc.values[CoreValue.OPTIMISM] - 1
    return (
        config.value_weight * alignment(npc, item, config)
        + config.tag_weight * bool(matching_tags(npc, item))
        + config.sentiment_weight * (item.sentiment or 0.0) * optimism
    )
