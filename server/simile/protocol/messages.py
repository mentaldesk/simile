from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from simile.schema import (
    VILLAGE_MAP,
    Bionic,
    BodyPart,
    Conversation,
    Facing,
    Id,
    JournalEntry,
    Key,
    Line,
    Model,
    Pile,
    Player,
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
    flushed: bool = Field(
        default=False,
        exclude_if=lambda flushed: not flushed,
        description="Whether the client shows a flush on the speaker: the line is a lie, as code "
        "decides it, and the player has the infrared eye. Left out unless true.",
    )


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


class Meal(Model):
    """A meal the player can have where they stand, by sending `eat` without an item."""

    place: Id = Field(description="Where: their home's location id, or a shop's.")
    name: str = Field(
        min_length=1,
        description='The place as the player sees it: "home", or a shop\'s name, e.g. "Golden '
        'Bowl Noodles".',
    )
    price: float = Field(ge=0, allow_inf_nan=False, description="What it costs. Nothing at home.")


class Fitting(Model):
    """A bionic the buyer fits, by `fit`, for its `price` and one of the player's `parts`."""

    bionic: Bionic
    name: str = Field(
        min_length=1, description='The bionic as the player sees it, e.g. "Hydraulic legs".'
    )
    price: float = Field(ge=0, allow_inf_nan=False)
    parts: list[BodyPart] = Field(
        min_length=1,
        description="The parts of their body it can go in place of, any one of which they give "
        'up for it: `["legs"]`, or `["left_eye", "right_eye"]` for an eye.',
    )

    @model_validator(mode="before")
    @classmethod
    def _parts_it_replaces(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(parts := data.get("parts"), list):
            named = [part for part in parts if isinstance(part, str)]
            if len(set(named)) != len(named):
                raise ValueError("a fitting names each part once")
            bionic = data.get("bionic")
            fits = Bionic(bionic).replaces if isinstance(bionic, str) and bionic in Bionic else None
            if fits is not None and (wrong := [part for part in named if part not in fits]):
                raise ValueError(f"{bionic} can't replace {', '.join(wrong)}")
        return data


class Buyer(Model):
    """Who trades where the player stands: buys with `sell` and `sell_part`, and fits with `fit`."""

    place: Id = Field(description='Where: a location id, e.g. "scrap_stall" or "clinic".')
    name: str = Field(
        min_length=1,
        description='The buyer as the player sees it, e.g. "The scrap trader".',
    )
    prices: dict[Key, Annotated[float, Field(ge=0, allow_inf_nan=False)]] = Field(
        description="What it pays for one of each thing they carry that it buys, by item `id`. "
        "Empty when they carry nothing it buys."
    )
    parts: dict[BodyPart, Annotated[float, Field(ge=0, allow_inf_nan=False)]] = Field(
        default={},
        exclude_if=lambda parts: not parts,
        description="What it pays for each part of their body it would buy now, by `sell_part`, "
        'by `Body` field, e.g. `{"left_kidney": 100}`. The clinic\'s doctor buys one kidney, '
        "never the second. Left out while it would buy none.",
    )
    fittings: list[Fitting] = Field(
        default=[],
        exclude_if=lambda fittings: not fittings,
        description="The bionics it would fit now, by `fit`, whether or not they can pay, each "
        "once. Left out while there are none.",
    )

    @model_validator(mode="after")
    def _each_bionic_once(self) -> Self:
        bionics = [fitting.bionic for fitting in self.fittings]
        if len(set(bionics)) != len(bionics):
            raise ValueError("a buyer offers each bionic once")
        return self


class PlayerStateMessage(Model):
    """The player's money, what they carry, their body and their hunger, but never their humanity,
    with the meal on offer and the buyer where they stand, and what's lying in the world for them
    to pick up. Sent after the snapshot on connect, and whenever any of it changes."""

    type: Literal["player_state"] = "player_state"
    player: Player
    meal: Meal | None = Field(
        default=None,
        exclude_if=lambda meal: meal is None,
        description="The meal on offer where they stand: at home, or at a shop that's serving. "
        "Left out where there's none.",
    )
    buyer: Buyer | None = Field(
        default=None,
        exclude_if=lambda buyer: buyer is None,
        description="Who buys where they stand, such as the scrap trader at their stall. Left out "
        "where there's none.",
    )
    piles: list[Pile] = Field(
        default=[],
        exclude_if=lambda piles: not piles,
        description="What's lying in the world for them to pick up, on every map, besides what "
        "they left (`player.left`): salvage and secrets. Left out while there's none.",
    )


class PlayerCollapsedMessage(Model):
    """The player starved and collapsed. They wake at home, at `position`, still hungry, with
    their lamp. Everything else they carried stays where they fell, in `player_state`'s `left`."""

    type: Literal["player_collapsed"] = "player_collapsed"
    position: Position


class JournalMessage(Model):
    """What the player has learned about the incident, in the order they learned it, with the
    leads still open. Sent after the snapshot on connect, and whenever an entry is added or a lead
    is followed."""

    type: Literal["journal"] = "journal"
    entries: list[JournalEntry]


class PlayerMoveMessage(Model):
    """A position without `map` is on the village. Side-view maps have no village, so there the
    server ignores it, as it ignores any unknown map.

    On a side-view map the position can be mid-air, jumping or falling. The server keeps one in
    open air over somewhere to land if it's within the farthest, highest jump the player can make
    from somewhere to stand (a run jump with Space held, taking off as late as coyote time
    allows), or if it's lower than the last position it kept on that map and within that jump's
    reach of it along the row, as in a fall from any height. It ignores a position nobody could
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


class EatMessage(Model):
    """The server ignores it if there's nothing to eat, or they can't pay."""

    type: Literal["eat"] = "eat"
    item: Id | None = Field(
        description="A food item they carry, by its `id`, or null for the meal on offer where "
        "they stand, `player_state`'s `meal`."
    )


class PickUpMessage(Model):
    """Picks up, from the nearest pile within reach of the player, its money and each item that
    still fits under their carry limit, in order. Any that don't fit stay in the pile."""

    type: Literal["pick_up"] = "pick_up"


class LampMessage(Model):
    """Switches the lamp the player carries on or off. The server ignores it if they carry no
    lamp, and for switching on a flat one."""

    type: Literal["lamp"] = "lamp"
    on: bool


class SellMessage(Model):
    """Sells to the buyer where the player stands, `player_state`'s `buyer`, for its price. The
    server ignores it if there's no buyer, or they carry nothing it buys."""

    type: Literal["sell"] = "sell"
    item: Id | None = Field(
        description="One thing they carry, by its `id`, or null for everything they carry that "
        "the buyer buys."
    )


class SellPartMessage(Model):
    """Sells a part of their body to the buyer where they stand, at its `buyer.parts` price."""

    type: Literal["sell_part"] = "sell_part"
    part: BodyPart


class FitMessage(Model):
    """Has the buyer where they stand fit a bionic in place of `part`, for its `fittings` price."""

    type: Literal["fit"] = "fit"
    bionic: Bionic
    part: BodyPart


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
    | PaintingsMessage
    | PlayerStateMessage
    | JournalMessage
    | PlayerCollapsedMessage,
    Field(discriminator="type"),
]

type ClientMessage = Annotated[
    PlayerMoveMessage
    | PlayerSayMessage
    | WatchNpcMessage
    | ListNewsMessage
    | ReadNewsMessage
    | ListWorksMessage
    | ReadWorkMessage
    | EatMessage
    | PickUpMessage
    | SellMessage
    | LampMessage
    | SellPartMessage
    | FitMessage,
    Field(discriminator="type"),
]

type Message = ServerMessage | ClientMessage

client_messages: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
server_messages: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
