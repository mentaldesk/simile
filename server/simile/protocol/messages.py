from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from simile.schema import (
    VILLAGE_MAP,
    Conversation,
    Facing,
    Id,
    Key,
    Line,
    Model,
    Pose,
    Timestamp,
)
from simile.schema.news import LongSummary


def _not_required(*names: str) -> Callable[[dict[str, Any]], None]:
    def drop(schema: dict[str, Any]) -> None:
        schema["required"] = [name for name in schema["required"] if name not in names]
        for name in names:
            # Beside a $ref, a default makes json-schema-to-typescript declare a copy, like Pose1.
            if "$ref" in (field := schema["properties"][name]):
                del field["default"]

    return drop


class Position(Model):
    """Where an entity stands, in tiles: (4, 6) is on tile (4, 6). Fractions are mid-step. On a
    side-view map, x runs along the street and y counts rows down from the top, and fractions are
    mid-step or mid-climb, or for the player, mid-air in a jump or a fall."""

    # The client uses Position as its plain point type, so map stays optional in TypeScript.
    model_config = ConfigDict(json_schema_extra=_not_required("map"))

    x: float
    y: float
    map: Key = Field(
        default=VILLAGE_MAP,
        description="The map it's on. The server always sends it, and a client that leaves it "
        "out means the village.",
    )


class EntityKind(StrEnum):
    NPC = "npc"
    PLAYER = "player"


# Optional in TypeScript, like Position.map, so existing client code still type-checks.
_POSE_NOT_REQUIRED = ConfigDict(json_schema_extra=_not_required("pose", "facing"))


class Entity(Model):
    """The server always sends `pose` and `facing`. Missing, they're standing, facing south-east."""

    model_config = _POSE_NOT_REQUIRED

    id: Id
    kind: EntityKind
    name: str
    position: Position
    pose: Pose = Pose.STANDING
    facing: Facing = Facing.SOUTH_EAST


class SnapshotMessage(Model):
    """The whole world, sent on connect. Replaces anything the client had."""

    type: Literal["snapshot"] = "snapshot"
    time: Timestamp = Field(description="Sim time.")
    map_id: Key = Field(
        description="The map the player starts on: the village, or a street on side-view maps."
    )
    entities: list[Entity]
    conversations: list[Conversation] = Field(description="Only those still going on.")


class ClockMessage(Model):
    """The sim clock, sent after the snapshot, when the speed changes and every sim minute."""

    type: Literal["clock"] = "clock"
    time: Timestamp = Field(description="Sim time.")
    speed: float = Field(gt=0, description="Sim seconds per real second.")


class EntityMovedMessage(Model):
    """The server always sends `pose` and `facing`. Missing, they're standing, facing south-east.
    On a side-view map, someone on stairs or a ladder is `climbing`. Taking stairs, a ladder or a
    lift to another map is an `entity_moved` at its end, `climbing` or `riding`, held for the climb
    or ride, then one onto the other map, as through a door."""

    model_config = _POSE_NOT_REQUIRED

    type: Literal["entity_moved"] = "entity_moved"
    entity_id: Id
    position: Position
    pose: Pose = Pose.STANDING
    facing: Facing = Facing.SOUTH_EAST


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
    long_summary: LongSummary | None = Field(
        default=None,
        exclude_if=lambda long_summary: long_summary is None,
        description="Three or four short paragraphs of plain text, separated by blank lines. Left "
        "out when there isn't one, so the client shows `summary`.",
    )
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


class Notice(Model):
    """A short notice a shopkeeper, the `poster`, puts up at the terminals: an offer, an event or
    an invitation. It isn't a work."""

    notice_id: Key
    title: str
    text: str = Field(description="The notice itself, with its line breaks.")
    poster: Artist
    created: Timestamp = Field(description="Sim time.")


class WorksMessage(Model):
    """Residents' writing at the terminals, newest first, and the notice board. The reply to
    list_works and read_work."""

    type: Literal["works"] = "works"
    works: list[WrittenWork]
    notices: list[Notice] = Field(
        default=[], description="The notices up on the board, newest first. Apart from the works."
    )


class Face(StrEnum):
    """The way a wall faces. The iso camera sees only south and east faces, and a side-view map
    has only south faces, towards the camera."""

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
    "that tile's south edge (y + 1) or east edge (x + 1). On a side-view map, it's the standing "
    "cell at the wall's west end, on the street in front of it."
)


class Wall(Model):
    id: Id
    map: Key = Field(
        default=VILLAGE_MAP,
        exclude_if=lambda key: key == VILLAGE_MAP,
        description="The map it's on, such as a street. Left out on the village.",
    )
    x: int = Field(ge=0, description=WALL_TILE)
    y: int = Field(ge=0, description=WALL_TILE)
    width: int = Field(
        ge=1, description="In tiles, east from (x, y) for a south face or south for an east face."
    )
    face: Face
    bottom: float = Field(
        ge=0, description="The mural's lower edge, in storeys above the ground there."
    )
    top: float = Field(description="The mural's upper edge, in storeys above the ground there.")
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


class Painting(Model):
    work_id: Key
    title: str
    artist: Artist
    statement: str = Field(description="The artist on what it's saying.")
    image: str = Field(description="The URL of the painting's image. Each work has its own.")


class Frame(Model):
    id: Id = Field(description="The painting interactable's id.")
    map: Key = Field(description="The map the interactable is on.")
    painting: Painting | None = Field(description="Null while the frame is empty.")


class PaintingsMessage(Model):
    """Every frame and the painting in it. Sent on connect and whenever a painting changes."""

    type: Literal["paintings"] = "paintings"
    frames: list[Frame]


class PlayerMoveMessage(Model):
    """A position without `map` is on the village. Side-view maps have no village, so there the
    server ignores it, as it ignores any unknown map. On a side-view map the position can be
    mid-air, jumping or falling: the server keeps one in open air over somewhere to land, no
    higher than a jump from somewhere to stand within a jump's reach, and ignores one nobody could
    be at."""

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
    | MuralsMessage
    | PaintingsMessage,
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
