from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, TypeAdapter

from simile.schema import Conversation, Id, Key, Line, Model, Timestamp


class Position(Model):
    """Where an entity stands, in tiles: (4, 6) is on tile (4, 6). Fractions are mid-step."""

    x: float
    y: float


class EntityKind(StrEnum):
    NPC = "npc"
    PLAYER = "player"


class Entity(Model):
    id: Id
    kind: EntityKind
    name: str
    position: Position


class SnapshotMessage(Model):
    """The whole world, sent on connect. Replaces anything the client had."""

    type: Literal["snapshot"] = "snapshot"
    time: Timestamp = Field(description="Sim time.")
    map_id: Key
    entities: list[Entity]
    conversations: list[Conversation] = Field(description="Only those still going on.")


class EntityMovedMessage(Model):
    type: Literal["entity_moved"] = "entity_moved"
    entity_id: Id
    position: Position


class ConversationStartedMessage(Model):
    type: Literal["conversation_started"] = "conversation_started"
    conversation: Conversation


class ConversationEndedMessage(Model):
    type: Literal["conversation_ended"] = "conversation_ended"
    conversation_id: Key
    ended: Timestamp


class LineMessage(Model):
    type: Literal["line"] = "line"
    line: Line
    voiced: bool = Field(description="Whether audio_chunk frames will follow for this line.")


class NpcStateMessage(Model):
    """Debug state for the overlay. The fields in `state` are up to the modules that send them."""

    type: Literal["npc_state"] = "npc_state"
    npc_id: Id
    state: dict[str, JsonValue]


class PlayerMoveMessage(Model):
    type: Literal["player_move"] = "player_move"
    position: Position


class PlayerSayMessage(Model):
    type: Literal["player_say"] = "player_say"
    text: str = Field(min_length=1)
    target: Id = Field(description="The NPC the player is talking to.")


class WatchNpcMessage(Model):
    type: Literal["watch_npc"] = "watch_npc"
    npc_id: Id | None = Field(description="The NPC to send npc_state for, or null to stop.")


type ServerMessage = Annotated[
    SnapshotMessage
    | EntityMovedMessage
    | ConversationStartedMessage
    | ConversationEndedMessage
    | LineMessage
    | NpcStateMessage,
    Field(discriminator="type"),
]

type ClientMessage = Annotated[
    PlayerMoveMessage | PlayerSayMessage | WatchNpcMessage,
    Field(discriminator="type"),
]

type Message = ServerMessage | ClientMessage

client_messages: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
server_messages: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
