from dataclasses import dataclass, field

from simile.memory import Record
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.reflection.extraction import (
    Context,
    Deed,
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
        deeds = _deeds(npc, reflection, context)[: config.events]
        for other in context.others(npc):
            events = _events(
                npc, other, [deed for by, deed in deeds if by == other], context, config
            )
            result.after[(npc, other)] = _feel(result.after[(npc, other)], events, context)
            result.events += events
        if reflection is None:
            continue
        flags = [
            (about, new)
            for new in reflection.flags_opened
            if (about := context.who(new.about)) not in (None, npc) and new.description.strip()
        ]
        for about, new in flags[: config.flags]:
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

    for npc, reflection in reflections.items():
        for ref in reflection.flags_resolved:
            flag = context.flags.get(ref.strip().upper())
            if flag is None or flag.owner != npc:
                continue
            key = (flag.owner, flag.about)
            if any(f.id == flag.id and f.resolved is None for f in result.after[key].flags):
                result.after[key] = resolve_flag(result.after[key], flag.id, now)
    return result


def _deeds(npc: Id, reflection: Reflection | None, context: Context) -> list[tuple[Id, Deed]]:
    return [
        (by, deed)
        for deed in (reflection.events if reflection else [])
        if (by := context.who(deed.by)) not in (None, npc) and deed.action.strip()
    ]


def _events(
    npc: Id, actor: Id, deeds: list[Deed], context: Context, config: ReflectionConfig
) -> list[InteractionEvent]:
    """Scaled so that however many there are, they weigh no more than `max_magnitude`."""
    total = sum(deed.magnitude for deed in deeds)
    scale = min(1.0, config.max_magnitude / total) if total else 1.0
    return [
        InteractionEvent(
            actor=actor,
            target=npc,
            action=deed.action.strip(),
            aspects=list(dict.fromkeys(deed.aspects)),
            valence=deed.valence,
            magnitude=deed.magnitude * scale,
            timestamp=context.now,
            conversation_id=context.conversation.id,
        )
        for deed in deeds
    ]


def _feel(rel: Relationship, events: list[InteractionEvent], context: Context) -> Relationship:
    """Events apply at the pair's familiarity going in, which then grows once."""
    familiarity = rel.familiarity
    for event in events:
        rel = apply_event(rel, event, context.now).model_copy(update={"familiarity": familiarity})
    contact = InteractionEvent(
        actor=rel.about,
        target=rel.owner,
        action="talked",
        aspects=[],
        valence=0,
        magnitude=0,
        timestamp=context.now,
        conversation_id=context.conversation.id,
    )
    return apply_event(rel, contact, context.now)


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
