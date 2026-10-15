from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    pass


@dataclass(frozen=True)
class EntityMoved(Event):
    entity_id: str
    x: float
    y: float


@dataclass(frozen=True)
class ConversationStarted(Event):
    conversation_id: str
    participant_ids: tuple[str, ...]


@dataclass(frozen=True)
class LineSpoken(Event):
    conversation_id: str
    speaker_id: str
    text: str


@dataclass(frozen=True)
class ConversationEnded(Event):
    conversation_id: str
