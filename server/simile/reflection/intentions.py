import logging
import re
from collections.abc import Mapping
from datetime import datetime, timedelta

from simile.behaviour import Options
from simile.behaviour.intentions import deed
from simile.conversation.temptation import BROKE, BROKEN
from simile.memory import Record
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.reflection.extraction import Context, Extraction, Intent, Relationships, relationship
from simile.schema import (
    PLAYER_ID,
    Aspect,
    Flag,
    FlagKind,
    Id,
    Intention,
    IntentionKind,
    InteractionEvent,
    Memory,
    MemoryKind,
    Npc,
    Relationship,
)
from simile.social import apply_events, open_flag, resolve_flag

logger = logging.getLogger(__name__)

KINDS = {kind.value: kind for kind in IntentionKind}
WHEN = re.compile(r"^\s*(?:(today|tomorrow)\s+)?(?:at\s+)?(\d{1,2})[:.](\d{2})\s*$", re.IGNORECASE)
NOW = re.compile(r"^\s*(?:now|right now|straight away|now-ish)\s*$", re.IGNORECASE)


def intentions(
    context: Context, extraction: Extraction, config: ReflectionConfig = DEFAULT_CONFIG
) -> list[Intention]:
    """What the residents said they'd do that B1 can act on, at most `intentions` each. Drops
    any whose resident, kind, target or time doesn't check out against the map and the cast."""
    found: list[Intention] = []
    for intent in extraction.intentions:
        intention = _intention(intent, context, config, len(found) + 1)
        if intention is None:
            logger.debug("%s: dropped %r", context.conversation.id, intent)
            continue
        if sum(i.owner == intention.owner for i in found) < config.intentions:
            found.append(intention)
    return found


def due(when: str, now: datetime, config: ReflectionConfig = DEFAULT_CONFIG) -> datetime | None:
    """When `when` ("now", "today 15:00", "tomorrow 09:00", or a bare time, which is the next
    one) falls, or None if it's vague or beyond `horizon`."""
    if NOW.match(when):
        return now
    found = WHEN.match(when)
    if found is None:
        return None
    day, hour, minute = found[1], int(found[2]), int(found[3])
    if hour > 23 or minute > 59:
        return None
    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day and day.lower() == "tomorrow":
        at += timedelta(days=1)
    elif at <= now:
        at = now if day else at + timedelta(days=1)
    return at if at - now <= config.horizon else None


def _intention(
    intent: Intent, context: Context, config: ReflectionConfig, n: int
) -> Intention | None:
    owner = context.who(intent.who)
    kind = KINDS.get(intent.kind.strip().lower())
    description = " ".join(intent.description.split())[: config.description]
    if owner not in context.npcs or owner not in context.options or kind is None:
        return None
    when = due(intent.when, context.now, config)
    if when is None or not description:
        return None
    target = _target(kind, intent.target, owner, context.options[owner], context)
    if target is False:
        return None
    promised = [p for name in intent.promised_to if (p := context.who(name)) not in (None, owner)]
    expires = when + (config.expire_now if when == context.now else config.expire_later)
    return Intention(
        id=f"{context.conversation.id}/{owner}/{n}",
        owner=owner,
        kind=kind,
        target=target,
        description=description,
        promised_to=list(dict.fromkeys(promised)),
        created=context.now,
        due=when,
        expires=expires,
        conversation_id=context.conversation.id,
    )


def _target(
    kind: IntentionKind, text: str | None, owner: Id, options: Options, context: Context
) -> Id | None | bool:
    """The id `text` names for `kind`, None where none is needed, or False if it won't do."""
    match kind:
        case IntentionKind.GO:
            return _among(text, options.places) or False
        case IntentionKind.SEEK:
            found = _person(text, context)
            return found if found not in (None, owner) else False
        case IntentionKind.CREATE:
            if options.medium is None:
                return False
            return _among(text, options.making)
        case IntentionKind.NEWS:
            return _among(text, options.terminals)


def _among(text: str | None, named: Mapping[Id, str]) -> Id | None:
    if not text:
        return None
    key = text.strip().lower()
    return next((id for id, name in named.items() if key in (id, name.lower())), None)


def _person(text: str | None, context: Context) -> Id | None:
    if not text:
        return None
    if found := context.who(text):
        return found
    key = text.strip().lower()
    if key in (PLAYER_ID, "visitor"):
        return PLAYER_ID
    for npc in context.residents.values():
        if key in (npc.id, npc.name.lower(), npc.name.split()[0].lower()):
            return npc.id
    return None


def broken(
    intention: Intention,
    npcs: Mapping[Id, Npc],
    store: Relationships,
    now: datetime,
    config: ReflectionConfig = DEFAULT_CONFIG,
) -> list[Record]:
    """What a promise left to expire leaves behind: the resident's memory of not doing it and
    each promisee's of being let down. A resident promised also holds a `broken_promise` in
    place of the promise from that conversation, and trusts them less. Nothing if nobody was
    promised."""
    owner = npcs.get(intention.owner)
    if owner is None or not intention.promised_to:
        return []
    said = deed(intention)
    first = owner.name.split()[0]
    told = ", ".join(_name(npcs, p, config) for p in intention.promised_to)
    records: list[Record] = [
        _memory(intention, intention.owner, BROKE.format(told=told, deed=said), now, config)
    ]
    for promised in intention.promised_to:
        records.append(
            _memory(intention, promised, f"{first} told me they'd {said}, and didn't.", now, config)
        )
        npc = npcs.get(promised)
        if npc is None:
            continue
        before = relationship(store, npc, owner.id, now)
        rel = _settle(before, intention, now)
        rel = open_flag(
            rel,
            Flag(
                id=f"{intention.id}/broken",
                kind=FlagKind.BROKEN_PROMISE,
                owner=promised,
                about=owner.id,
                description=said,
                created=now,
            ),
        )
        event = InteractionEvent(
            actor=owner.id,
            target=promised,
            action=f"broke a promise: {said}",
            aspects=[Aspect.TRUST],
            valence=config.broken_promise_valence,
            magnitude=config.broken_promise_magnitude,
            timestamp=now,
            conversation_id=intention.conversation_id,
        )
        after = apply_events(rel, [event], now)
        records += [event, after.model_copy(update={"familiarity": before.familiarity})]
    return records


def kept(
    intention: Intention, npcs: Mapping[Id, Npc], store: Relationships, now: datetime
) -> list[Record]:
    """Each promisee's promise flag from that conversation, resolved."""
    found: list[Record] = []
    for promised in intention.promised_to:
        npc = npcs.get(promised)
        if npc is None:
            continue
        before = relationship(store, npc, intention.owner, now)
        after = _settle(before, intention, now)
        if after is not before:
            found.append(after)
    return found


def _settle(rel: Relationship, intention: Intention, now: datetime) -> Relationship:
    """`rel` with the promise from the intention's conversation resolved, if it holds just one."""
    if intention.conversation_id is None:
        return rel
    prefix = f"{intention.conversation_id}/"
    promises = [
        flag
        for flag in rel.flags
        if flag.kind is FlagKind.PROMISE and flag.resolved is None and flag.id.startswith(prefix)
    ]
    return resolve_flag(rel, promises[0].id, now) if len(promises) == 1 else rel


def _memory(
    intention: Intention, owner: Id, content: str, now: datetime, config: ReflectionConfig
) -> Memory:
    others = [intention.owner, *intention.promised_to]
    return Memory(
        owner=owner,
        kind=MemoryKind.OBSERVATION,
        content=content,
        salience=config.broken_salience,
        valence=config.broken_promise_valence,
        timestamp=now,
        about=[other for other in dict.fromkeys(others) if other != owner],
        topics=[BROKEN],
        conversation_id=intention.conversation_id,
    )


def _name(npcs: Mapping[Id, Npc], id: Id, config: ReflectionConfig) -> str:
    if id == PLAYER_ID:
        return config.player_name
    npc = npcs.get(id)
    return npc.name.split()[0] if npc else id
