from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, TypeAdapter, model_validator

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


class ClockMessage(Model):
    """The sim clock, sent after the snapshot, when the speed changes and every sim minute."""

    type: Literal["clock"] = "clock"
    time: Timestamp = Field(description="Sim time.")
    speed: float = Field(gt=0, description="Sim seconds per real second.")


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


class NewsArticle(Model):
    news_id: Key
    title: str
    source: str = Field(description='The feed it came from, e.g. "The Atlantic". May be empty.')
    summary: str = Field(description="Plain text.")
    url: str = Field(description="The original article.")
    read: bool = Field(description="Whether the player has read it.")


class NewsMessage(Model):
    """The articles at the news terminals, newest first. The reply to list_news and read_news."""

    type: Literal["news"] = "news"
    articles: list[NewsArticle]


class Artist(Model):
    id: Id
    name: str


class WrittenWork(Model):
    work_id: Key
    title: str
    artist: Artist
    form: str = Field(description='What the artist makes, e.g. "short poems about the river".')
    text: str = Field(description="The piece itself, with its line breaks.")
    statement: str = Field(description="The artist on what it's saying.")
    created: Timestamp = Field(description="Sim time.")
    read: bool = Field(description="Whether the player has read it.")


class WorksMessage(Model):
    """Residents' writing at the terminals, newest first. The reply to list_works and read_work."""

    type: Literal["works"] = "works"
    works: list[WrittenWork]


class Face(StrEnum):
    """The way a wall faces. The iso camera sees only south and east faces."""

    SOUTH = "south"
    EAST = "east"


class Mural(Model):
    work_id: Key
    title: str
    artist: Artist
    statement: str = Field(description="The artist on what it's saying.")
    image: str = Field(description="The URL of the mural's image, /api/works/<work_id>.png.")


WALL_TILE = (
    "(x, y) is the building's tile at the west end of a south face or the north end of an east "
    "face: on its south row or east column, whatever storeys the mural spans. The face runs along "
    "that tile's south edge (y + 1) or east edge (x + 1)."
)


class Wall(Model):
    id: Id
    x: int = Field(ge=0, description=WALL_TILE)
    y: int = Field(ge=0, description=WALL_TILE)
    width: int = Field(
        ge=1, description="In tiles, east from (x, y) for a south face or south for an east face."
    )
    face: Face
    bottom: float = Field(ge=0, description="The mural's lower edge, in storeys above the ground.")
    top: float = Field(description="The mural's upper edge, in storeys above the ground.")
    mural: Mural | None = Field(description="Null while the wall is blank.")

    @model_validator(mode="after")
    def _top_above_bottom(self) -> Self:
        if self.top <= self.bottom:
            raise ValueError("top must be above bottom")
        return self


class MuralsMessage(Model):
    """Every mural wall and what's on it. Sent on connect and whenever a mural changes."""

    type: Literal["murals"] = "murals"
    walls: list[Wall]


class PlayerMoveMessage(Model):
    type: Literal["player_move"] = "player_move"
    position: Position


class PlayerSayMessage(Model):
    type: Literal["player_say"] = "player_say"
    text: str = Field(min_length=1)
    target: Id = Field(description="The NPC the player is talking to.")


class ListNewsMessage(Model):
    type: Literal["list_news"] = "list_news"


class ReadNewsMessage(Model):
    type: Literal["read_news"] = "read_news"
    news_id: Key = Field(description="The article the player reads.")


class ListWorksMessage(Model):
    type: Literal["list_works"] = "list_works"


class ReadWorkMessage(Model):
    type: Literal["read_work"] = "read_work"
    work_id: Key = Field(description="The work the player reads.")


class WatchNpcMessage(Model):
    type: Literal["watch_npc"] = "watch_npc"
    npc_id: Id | None = Field(description="The NPC to send npc_state for, or null to stop.")


type ServerMessage = Annotated[
    SnapshotMessage
    | ClockMessage
    | EntityMovedMessage
    | ConversationStartedMessage
    | ConversationEndedMessage
    | LineMessage
    | NpcStateMessage
    | NewsMessage
    | WorksMessage
    | MuralsMessage,
    Field(discriminator="type"),
]

type ClientMessage = Annotated[
    PlayerMoveMessage
    | PlayerSayMessage
    | WatchNpcMessage
    | ListNewsMessage
    | ReadNewsMessage
    | ListWorksMessage
    | ReadWorkMessage,
    Field(discriminator="type"),
]

type Message = ServerMessage | ClientMessage

client_messages: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
server_messages: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
