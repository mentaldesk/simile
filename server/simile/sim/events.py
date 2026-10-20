from dataclasses import dataclass

from simile.schema import Conversation, Facing, Id, Key, Line, Pose


@dataclass(frozen=True)
class Event:
    pass


@dataclass(frozen=True)
class EntityMoved(Event):
    entity: Id
    x: float
    y: float
    map: Key
    pose: Pose = Pose.STANDING
    facing: Facing = Facing.SOUTH_EAST


@dataclass(frozen=True)
class ConversationStarted(Event):
    conversation: Conversation


@dataclass(frozen=True)
class LineSpoken(Event):
    line: Line


@dataclass(frozen=True)
class ConversationEnded(Event):
    conversation: Conversation
