from dataclasses import dataclass, field

from simile.memory import Record
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.reflection.extraction import (
    Context,
    Extraction,
    Reflection,
    Relationships,
    relationship,
)
from simile.schema import Flag, Id, InteractionEvent, Memory, MemoryKind, Relationship
from simile.social import apply_event, open_flag, resolve_flag


@dataclass
class Outcome:
    """What a conversation changed, ready to store in one `MemoryStore.add`."""

    events: list[InteractionEvent] = field(default_factory=list)
    memories: list[Memory] = field(default_factory=list)
    before: dict[tuple[Id, Id], Relationship] = field(default_factory=dict)
    """Each relationship as it stood at the end of the conversation, before it counted."""
    after: dict[tuple[Id, Id], Relationship] = field(default_factory=dict)

    @property
    def records(self) -> list[Record]:
        return [*self.events, *self.memories, *self.after.values()]


def outcome(
    context: Context,
    extraction: Extraction,
    store: Relationships,
    config: ReflectionConfig = DEFAULT_CONFIG,
) -> Outcome:
    """Apply what each NPC made of the conversation to how they feel about the others. Reads
    the relationships afresh, since others may have changed while the LLM was busy."""
    now, conversation = context.now, context.conversation
    result = Outcome()
    for npc in context.npcs.values():
        for other in context.others(npc.id):
            result.before[(npc.id, other)] = relationship(store, npc, other, now)
    result.after.update(result.before)

    reflections: dict[Id, Reflection] = {}
    for reflection in extraction.reflections:
        npc = context.who(reflection.npc)
        if npc in context.npcs and npc not in reflections:
            reflections[npc] = reflection

    opened = 0
    for npc in context.npcs:
        reflection = reflections.get(npc)
        moved: set[Id] = set()
        for deed in reflection.events[: config.events] if reflection else []:
            actor = context.who(deed.by)
            if actor is None or actor == npc or not deed.action.strip():
                continue
            event = InteractionEvent(
                actor=actor,
                target=npc,
                action=deed.action.strip(),
                aspects=list(dict.fromkeys(deed.aspects)),
                valence=deed.valence,
                magnitude=deed.magnitude,
                timestamp=now,
                conversation_id=conversation.id,
            )
            result.after[(npc, actor)] = apply_event(result.after[(npc, actor)], event, now)
            result.events.append(event)
            moved.add(actor)
        for other in context.others(npc):
            if other not in moved:
                result.after[(npc, other)] = apply_event(
                    result.after[(npc, other)], _contact(other, npc, context), now
                )
        if reflection is None:
            continue
        for new in reflection.flags_opened[: config.flags]:
            about = context.who(new.about)
            if about is None or about == npc or not new.description.strip():
                continue
            opened += 1
            flag = Flag(
                id=f"{conversation.id}/{opened}",
                kind=new.kind,
                owner=npc,
                about=about,
                description=new.description.strip(),
                created=now,
            )
            result.after[(npc, about)] = open_flag(result.after[(npc, about)], flag)
        if reflection.summary.strip():
            result.memories.append(_memory(npc, reflection, context, config))

    for reflection in reflections.values():
        for ref in reflection.flags_resolved:
            flag = context.flags.get(ref.strip().upper())
            if flag is None:
                continue
            key = (flag.owner, flag.about)
            if any(f.id == flag.id and f.resolved is None for f in result.after[key].flags):
                result.after[key] = resolve_flag(result.after[key], flag.id, now)
    return result


def _contact(actor: Id, target: Id, context: Context) -> InteractionEvent:
    """A conversation with no event worth noting still counts as contact, for familiarity."""
    return InteractionEvent(
        actor=actor,
        target=target,
        action="talked",
        aspects=[],
        valence=0,
        magnitude=0,
        timestamp=context.now,
        conversation_id=context.conversation.id,
    )


def _memory(npc: Id, reflection: Reflection, context: Context, config: ReflectionConfig) -> Memory:
    topics = [topic.strip().lower() for topic in reflection.topics if topic.strip()]
    return Memory(
        owner=npc,
        kind=MemoryKind.CONVERSATION,
        content=reflection.summary.strip(),
        salience=reflection.salience,
        valence=reflection.valence,
        timestamp=context.now,
        about=context.others(npc),
        topics=list(dict.fromkeys(topics))[: config.topics],
        conversation_id=context.conversation.id,
    )
