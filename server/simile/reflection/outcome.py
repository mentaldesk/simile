from dataclasses import dataclass, field

from simile.conversation.temptation import Lie
from simile.memory import Record
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.reflection.extraction import (
    Context,
    Deed,
    Extraction,
    Reflection,
    Relationships,
    owner_and_about,
    relationship,
)
from simile.reflection.loans import Payment
from simile.schema import (
    Aspect,
    Flag,
    FlagKind,
    Id,
    Intention,
    InteractionEvent,
    Memory,
    MemoryKind,
    Relationship,
)
from simile.social import apply_events, lent, open_flag, resolve_flag


@dataclass
class Outcome:
    """What a conversation changed, ready to store in one `MemoryStore.add`."""

    events: list[InteractionEvent] = field(default_factory=list)
    memories: list[Memory] = field(default_factory=list)
    before: dict[tuple[Id, Id], Relationship] = field(default_factory=dict)
    """Each relationship as it stood at the end of the conversation, before it counted."""
    after: dict[tuple[Id, Id], Relationship] = field(default_factory=dict)
    intentions: list[Intention] = field(default_factory=list)
    """What the residents said they'd do that B1 took on."""

    @property
    def records(self) -> list[Record]:
        return [*self.events, *self.memories, *self.after.values()]


def outcome(
    context: Context,
    extraction: Extraction,
    store: Relationships,
    config: ReflectionConfig = DEFAULT_CONFIG,
    *,
    payment: Payment | None = None,
) -> Outcome:
    """Apply what each NPC made of the conversation to how they feel about the others, with the
    debt flag of a `payment` already made. Reads the relationships afresh, since others may have
    changed while the LLM was busy. A loan's flag closes only when it's paid back."""
    now = context.now
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

    opened = _flags(extraction, context, config)
    told = _told(extraction, context)
    for npc in context.npcs:
        reflection = reflections.get(npc)
        deeds = _deeds(npc, reflection, context)[: config.events]
        for other in context.others(npc):
            theirs = [deed for by, deed in deeds if by == other]
            theirs += _breaches(npc, other, theirs, opened, config)
            theirs += _caught(npc, other, theirs, told, config)
            events = _events(npc, other, theirs, context, config)
            result.after[(npc, other)] = apply_events(result.after[(npc, other)], events, now)
            result.events += events
        if reflection is not None and reflection.summary.strip():
            result.memories.append(_memory(npc, reflection, context, config))
    result.memories += [memory for lie in told for memory in _remembered(lie, context, config)]

    settled: set[tuple[Id, Id]] = set()
    for ref in extraction.flags_resolved:
        flag = context.flags.get(ref.strip().upper())
        if flag is None or lent(flag) is not None:
            continue
        key = (flag.owner, flag.about)
        if _still_open(result.after[key], flag):
            result.after[key] = resolve_flag(result.after[key], flag.id, now)
            if flag.kind == FlagKind.PROMISE:
                settled.add(key)

    for flag in opened:
        key = (flag.owner, flag.about)
        if flag.kind != FlagKind.BROKEN_PROMISE or key in settled:
            continue
        listed = [
            f
            for f in context.flags.values()
            if f.kind == FlagKind.PROMISE and (f.owner, f.about) == key
        ]
        if len(listed) == 1 and _still_open(result.after[key], listed[0]):
            result.after[key] = resolve_flag(result.after[key], listed[0].id, now)
            settled.add(key)

    if payment is not None and payment.settles is not None:
        flag = payment.settles
        key = (flag.owner, flag.about)
        if _still_open(result.after[key], flag):
            result.after[key] = resolve_flag(result.after[key], flag.id, now)
    if payment is not None and payment.opens is not None:
        key = (payment.opens.owner, payment.opens.about)
        opened = [f for f in opened if f.kind != FlagKind.DEBT or (f.owner, f.about) != key]
        opened.append(payment.opens)

    for flag in opened:
        key = (flag.owner, flag.about)
        result.after[key] = open_flag(result.after[key], flag)
    return result


def _still_open(rel: Relationship, flag: Flag) -> bool:
    return any(f.id == flag.id and f.resolved is None for f in rel.flags)


def _breaches(
    npc: Id, other: Id, deeds: list[Deed], opened: list[Flag], config: ReflectionConfig
) -> list[Deed]:
    """A trust hit for each promise `other` broke to `npc`, unless `npc`'s own deeds already
    count against their trust in `other`."""
    if any(deed.valence < 0 and Aspect.TRUST in deed.aspects for deed in deeds):
        return []
    return [
        Deed(
            by=other,
            action=f"broke a promise: {flag.description}",
            aspects=[Aspect.TRUST],
            valence=config.broken_promise_valence,
            magnitude=config.broken_promise_magnitude,
        )
        for flag in opened
        if flag.kind == FlagKind.BROKEN_PROMISE and (flag.owner, flag.about) == (npc, other)
    ]


def _told(extraction: Extraction, context: Context) -> list[Lie]:
    refs = dict.fromkeys(ref.strip().upper() for ref in extraction.lies)
    return [context.lies[ref] for ref in refs if ref in context.lies]


def _caught(
    npc: Id, other: Id, deeds: list[Deed], told: list[Lie], config: ReflectionConfig
) -> list[Deed]:
    """A trust hit for each lie `other` told `npc` that `npc` knew wasn't true, unless `npc`'s
    own deeds already count against their trust in `other`."""
    if any(deed.valence < 0 and Aspect.TRUST in deed.aspects for deed in deeds):
        return []
    return [
        Deed(
            by=other,
            action=f"lied about {lie.subject}",
            aspects=[Aspect.TRUST],
            valence=config.lied_to_valence,
            magnitude=config.lied_to_magnitude,
        )
        for lie in told
        if lie.known and (lie.listener, lie.liar) == (npc, other)
    ]


def _remembered(lie: Lie, context: Context, config: ReflectionConfig) -> list[Memory]:
    """The liar remembers telling it, and a listener who knew better remembers being lied to."""
    memories = []
    if lie.liar in context.npcs:
        memories.append(
            Memory(
                owner=lie.liar,
                kind=MemoryKind.OBSERVATION,
                content=lie.admits,
                salience=config.lie_salience,
                valence=config.lie_valence,
                timestamp=context.now,
                about=[lie.listener],
                topics=["lie"],
                conversation_id=context.conversation.id,
                fact_id=lie.fact_id,
            )
        )
    if lie.known and lie.listener in context.npcs:
        memories.append(
            Memory(
                owner=lie.listener,
                kind=MemoryKind.OBSERVATION,
                content=f"{context.names[lie.liar]} lied to me about {lie.subject}.",
                salience=config.lied_to_salience,
                valence=config.lied_to_valence,
                timestamp=context.now,
                about=[lie.liar],
                topics=["lied to me"],
                conversation_id=context.conversation.id,
                fact_id=lie.fact_id,
            )
        )
    return memories


def _flags(extraction: Extraction, context: Context, config: ReflectionConfig) -> list[Flag]:
    """The new flags, at most `flags` per owner."""
    flags: list[Flag] = []
    for new in extraction.flags_opened:
        who, whom = context.who(new.who), context.who(new.whom)
        description = new.description.strip()
        if who is None or whom is None or who == whom or not description:
            continue
        owner, about = owner_and_about(new.kind, who, whom)
        if owner in context.npcs and sum(f.owner == owner for f in flags) < config.flags:
            flags.append(
                Flag(
                    id=f"{context.conversation.id}/{len(flags) + 1}",
                    kind=new.kind,
                    owner=owner,
                    about=about,
                    description=description,
                    created=context.now,
                )
            )
    return flags


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
