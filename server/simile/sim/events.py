from dataclasses import dataclass

from simile.schema import VILLAGE_MAP, Conversation, Id, Key, Line


@dataclass(frozen=True)
class Event:
    pass


@dataclass(frozen=True)
class EntityMoved(Event):
    entity: Id
    x: float
    y: float
    map: Key = VILLAGE_MAP


@dataclass(frozen=True)
class ConversationStarted(Event):
    conversation: Conversation


@dataclass(frozen=True)
class LineSpoken(Event):
    line: Line


@dataclass(frozen=True)
class ConversationEnded(Event):
    conversation: Conversation
