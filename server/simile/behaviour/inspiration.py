import re
from collections.abc import Iterable

from simile.behaviour.config import DEFAULT_CONFIG, BehaviourConfig
from simile.npc.values import ranked
from simile.schema import Memory, MemoryKind, Npc

WORD = re.compile(r"[a-z][a-z'-]*")
SMALL = frozenset({"about", "from", "into", "that", "their", "them", "they", "this", "with"})


def inspiring(memory: Memory, config: BehaviourConfig = DEFAULT_CONFIG) -> bool:
    """A conversation, an article read, or someone else's work read or seen. A work memory about
    nobody is of making their own."""
    if memory.kind not in config.inspiring:
        return False
    return memory.kind is not MemoryKind.WORK or bool(memory.about)


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def touches(topics: Iterable[str], keys: Iterable[str]) -> bool:
    """Whether a topic has one of `keys`, a word beginning with one, or a phrase of them."""
    keys = [key.lower() for key in keys]
    for topic in topics:
        found = words(topic)
        joined = " ".join(found)
        for key in keys:
            if " " in key or "-" in key:
                if key in joined:
                    return True
            elif any(word == key or (len(key) >= 4 and word.startswith(key)) for word in found):
                return True
    return False


def craft_words(npc: Npc, config: BehaviourConfig = DEFAULT_CONFIG) -> list[str]:
    """Their medium's words and the longer words of their craft's form."""
    if npc.craft is None:
        return []
    form = [singular(w) for w in words(npc.craft.form) if len(w) >= 4 and w not in SMALL]
    return [*config.craft_words.get(npc.craft.medium, ()), *form]


def singular(word: str) -> str:
    word = word.rstrip("'")
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def inspiration(memory: Memory, npc: Npc, config: BehaviourConfig = DEFAULT_CONFIG) -> float:
    """What a new memory adds to a crafter's inspiration, before the hourly cap: more for a
    stronger one (salience × intensity), and for one whose topics touch their craft or their
    strongest values."""
    if npc.craft is None or memory.owner != npc.id or not inspiring(memory, config):
        return 0.0
    intensity = config.calm + (1 - config.calm) * abs(memory.valence)
    share = 1.0
    if touches(memory.topics, craft_words(npc, config)):
        share += config.inspiration_craft
    strongest = [value for value, _ in ranked(npc.values)[: config.strongest]]
    if any(touches(memory.topics, config.value_words.get(value, ())) for value in strongest):
        share += config.inspiration_values
    bump = config.inspiration_weight * memory.salience * intensity * share
    return min(bump, config.inspiration_cap)
