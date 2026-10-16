from dataclasses import dataclass

from pydantic import JsonValue

from simile.behaviour import Behaviour
from simile.conversation import ConversationEngine
from simile.memory import MemoryStore
from simile.schema import Flag, Id, Line, Memory, Npc, Relationship
from simile.social import as_of

TOP_VALUES = 5
MAX_RELATIONSHIPS = 12
MAX_FLAGS = 4
MAX_MEMORIES = 6
MAX_LINES = 12
MAX_TEXT = 280


@dataclass
class Village:
    """Where the overlay reads an NPC's state from."""

    behaviour: Behaviour
    conversations: ConversationEngine
    memory: MemoryStore

    def npc_state(self, npc: Id) -> dict[str, JsonValue] | None:
        """What the overlay shows about `npc`, or None if there's no such NPC."""
        mind = self.behaviour.minds.get(npc)
        if mind is None:
            return None
        now = self.behaviour.clock.now
        relationships = sorted(
            (as_of(rel, now) for rel in self.memory.relationships(npc)),
            key=lambda rel: (-rel.familiarity, rel.about),
        )
        return {
            "name": mind.npc.name,
            "occupation": mind.npc.occupation,
            "time": now.isoformat(),
            **self.behaviour.state(npc),
            "values": top_values(mind.npc),
            "relationships": [relationship_row(rel) for rel in relationships[:MAX_RELATIONSHIPS]],
            "memories": [memory_row(m) for m in self.memory.recall(npc, now, k=MAX_MEMORIES)],
            "conversation": self.conversation(npc),
        }

    def conversation(self, npc: Id) -> dict[str, JsonValue] | None:
        state = self.conversations.state(npc)
        conversation_id = state.pop("conversation")
        if conversation_id is None:
            return None
        conversation = self.conversations.conversation(str(conversation_id))
        lines = conversation.lines[-MAX_LINES:] if conversation else []
        return {"id": conversation_id, **state, "lines": [line_row(spoken) for spoken in lines]}


def top_values(npc: Npc) -> dict[str, JsonValue]:
    ranked = sorted(npc.values.items(), key=lambda item: (-item[1], item[0]))
    return {value.value: round(score, 3) for value, score in ranked[:TOP_VALUES]}


def relationship_row(rel: Relationship) -> dict[str, JsonValue]:
    flags = sorted(
        rel.flags, key=lambda flag: (flag.resolved is not None, -flag.created.timestamp())
    )
    return {
        "about": rel.about,
        "like": round(rel.like, 3),
        "trust": round(rel.trust, 3),
        "respect": round(rel.respect, 3),
        "familiarity": round(rel.familiarity, 3),
        "flags": [flag_row(flag) for flag in flags[:MAX_FLAGS]],
    }


def flag_row(flag: Flag) -> dict[str, JsonValue]:
    return {
        "kind": flag.kind.value,
        "description": clip(flag.description),
        "open": flag.resolved is None,
    }


def memory_row(remembered: Memory) -> dict[str, JsonValue]:
    return {
        "kind": remembered.kind.value,
        "content": clip(remembered.content),
        "timestamp": remembered.timestamp.isoformat(),
        "salience": round(remembered.salience, 3),
        "valence": round(remembered.valence, 3),
    }


def line_row(spoken: Line) -> dict[str, JsonValue]:
    return {
        "speaker": spoken.speaker,
        "text": clip(spoken.text),
        "timestamp": spoken.timestamp.isoformat(),
    }


def clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"
