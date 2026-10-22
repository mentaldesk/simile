import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError
from pydantic.json_schema import JsonSchemaMode

from simile.protocol import (
    Artist,
    ClockMessage,
    ConversationEndedMessage,
    ConversationStartedMessage,
    EatMessage,
    EntityMovedMessage,
    Face,
    Frame,
    JournalMessage,
    LineMessage,
    ListNewsMessage,
    ListWorksMessage,
    Meal,
    Message,
    Mural,
    MuralsMessage,
    NewsArticle,
    NewsMessage,
    Notice,
    NpcStateMessage,
    Painting,
    PaintingsMessage,
    PickUpMessage,
    PlayerCollapsedMessage,
    PlayerMoveMessage,
    PlayerSayMessage,
    PlayerStateMessage,
    Position,
    ReadNewsMessage,
    ReadWorkMessage,
    Wall,
    WatchNpcMessage,
    WorksMessage,
    WrittenWork,
)
from simile.protocol.export import SCHEMA_FILE
from simile.protocol.fixtures import fixture_snapshot
from simile.protocol.messages import client_messages, server_messages
from simile.schema import (
    Bionic,
    Body,
    Facing,
    Item,
    ItemKind,
    JournalEntry,
    Lead,
    MapTile,
    Pile,
    Player,
    Pose,
    Source,
    SourceKind,
    lamp,
)

SNAPSHOT = fixture_snapshot(datetime(2026, 3, 14, 9, 10, 3, tzinfo=UTC))
CONVERSATION = SNAPSHOT.conversations[0]
ARTICLE = NewsArticle(
    news_id="https://bigthink.com/?p=900101",
    title="Drones to be regulated",
    source="Big Think",
    summary="The council votes on drone rules.",
    url="https://bigthink.com/drones",
    read=False,
)
LONG_SUMMARY = (
    "The council meets in May to vote on where delivery drones may fly.\n\n"
    "Residents near the depot want quiet hours. The couriers say the routes save time."
)
SUMMARISED = NewsArticle.model_validate(
    ARTICLE.model_dump() | {"news_id": "n3", "long_summary": LONG_SUMMARY}
)

VIKTOR = Artist(id="viktor", name="Viktor Petrov")
POEM = WrittenWork(
    work_id="work_1",
    title="The Footbridge",
    artist=VIKTOR,
    form="plain verse about old bridges",
    text="They built it for a hundred years.\nThe arch has held for ninety-one.",
    statement="Things last when people look after them.",
    created=datetime(2026, 3, 14, 8, 40, tzinfo=UTC),
    read=False,
)
NOTICE = Notice(
    notice_id="notice_1",
    title="Two-for-one flat whites",
    text="All afternoon, while the oat milk lasts.",
    poster=Artist(id="mirela", name="Mirela Popescu"),
    created=datetime(2026, 3, 14, 9, tzinfo=UTC),
)
WORKS = WorksMessage(
    works=[POEM.model_copy(update={"work_id": "work_3", "read": True}), POEM], notices=[NOTICE]
)
MURAL = Mural(
    work_id="work_2",
    title="Who Owns the Sky",
    artist=Artist(id="suki", name="Suki Tanaka"),
    statement="The sky was the one place nobody filled with forms.",
    image="/api/works/work_2.png",
)
SQUARE_WALL = Wall(
    id="square_north", x=12, y=8, width=4, face=Face.SOUTH, bottom=0, top=1, mural=MURAL
)
MURALS = MuralsMessage(
    walls=[
        SQUARE_WALL,
        Wall(id="park_east", x=30, y=14, width=3, face=Face.EAST, bottom=0.2, top=2, mural=None),
    ]
)
STREET_WALL = Wall(
    id="market_mural",
    map="market_street",
    x=20,
    y=11,
    width=5,
    face=Face.SOUTH,
    bottom=0,
    top=2,
    mural=MURAL,
)
STREET_MURALS = MuralsMessage(walls=[STREET_WALL])
PAINTING = Painting(
    work_id="work_4",
    title="Low Tide, Six O'Clock",
    artist=Artist(id="mei", name="Mei Lin"),
    statement="The mud flats are the only time the river slows down enough to look at.",
    image="/api/gallery/work_4.png",
)
FIRST_FRAME = Frame(id="painting_1", map="gallery", painting=PAINTING)
PAINTINGS = PaintingsMessage(
    frames=[FIRST_FRAME, Frame(id="painting_2", map="gallery", painting=None)]
)

SEATED = SNAPSHOT.model_copy(
    update={
        "entities": [
            SNAPSHOT.entities[0].model_copy(update={"pose": Pose.SITTING, "facing": Facing.WEST}),
            *SNAPSHOT.entities[1:],
        ]
    }
)
LOOKING = EntityMovedMessage(
    entity_id="viktor",
    position=Position(x=6, y=3, map="gallery"),
    pose=Pose.LOOKING,
    facing=Facing.NORTH,
)
CLIMBING = EntityMovedMessage(
    entity_id="kofi",
    position=Position(x=7, y=6.5, map="house_1"),
    pose=Pose.CLIMBING,
    facing=Facing.NORTH,
)
RIDING = EntityMovedMessage(
    entity_id="ingrid",
    position=Position(x=3, y=9, map="flats"),
    pose=Pose.RIDING,
    facing=Facing.SOUTH,
)

STARTING = PlayerStateMessage(player=Player())
DELVING = PlayerStateMessage(
    player=Player(
        money=120,
        items=[
            lamp().model_copy(update={"charge": 0.35, "on": True}),
            Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5),
            Item(id="noodles", kind=ItemKind.FOOD, name="Noodles", weight=0.5),
        ],
        body=Body(legs=Bionic.HYDRAULIC_LEGS, right_eye=Bionic.INFRARED_EYE, left_kidney="sold"),
        hunger=0.55,
    )
)

NOODLES = Meal(place="noodle_bar", name="Golden Bowl Noodles", price=10)
AT_THE_NOODLE_BAR = DELVING.model_copy(update={"meal": NOODLES})
WOKEN = PlayerStateMessage(
    player=Player(
        items=[],
        hunger=0.75,
        left=[Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[lamp()])],
    ),
    meal=Meal(place="maker_space", name="home", price=0),
)
COLLAPSED = PlayerCollapsedMessage(position=Position(x=13, y=2, map="maker_space_floor_0"))

FROM_THE_NOTES = JournalEntry(
    fact_id="notes",
    text="Aris wrote that R. came about the machines again, and said he'd make her regret it.",
    source=Source(kind=SourceKind.CLUE, id="aris_notes", name="Aris's notes"),
    learned=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
    flushed=None,
    leads=[Lead(fact_id="motive", text="Who's R.? Mirela knows everyone's business.")],
)
FROM_RAYMOND = JournalEntry(
    fact_id="attack",
    text="Raymond says he was at home going over the accounts all night.",
    source=Source(kind=SourceKind.RESIDENT, id="raymond", name="Raymond"),
    learned=datetime(2026, 3, 17, 14, tzinfo=UTC),
    flushed=True,
)
JOURNAL = JournalMessage(entries=[FROM_THE_NOTES, FROM_RAYMOND])

CLOCK = ClockMessage(time=SNAPSHOT.time, speed=60)
SERVER = [
    SNAPSHOT,
    EntityMovedMessage(entity_id="mei", position=Position(x=4.5, y=6)),
    EntityMovedMessage(entity_id="suki", position=Position(x=10, y=12, map="coffee_shop")),
    SEATED,
    LOOKING,
    CLIMBING,
    RIDING,
    ConversationStartedMessage(conversation=CONVERSATION.model_copy(update={"lines": []})),
    ConversationEndedMessage(
        conversation_id=CONVERSATION.id, ended=datetime(2026, 3, 14, 9, 11, tzinfo=UTC)
    ),
    LineMessage(line=CONVERSATION.lines[-1], voiced=True),
    LineMessage(line=CONVERSATION.lines[-1], voiced=False, flushed=True),
    NpcStateMessage(npc_id="mei", state={"goal": "coffee_shop", "values": {"connection": 0.92}}),
    NewsMessage(
        articles=[
            ARTICLE,
            ARTICLE.model_copy(update={"news_id": "n2", "read": True}),
            SUMMARISED,
        ]
    ),
    CLOCK,
    WORKS,
    MURALS,
    STREET_MURALS,
    PAINTINGS,
    STARTING,
    DELVING,
    AT_THE_NOODLE_BAR,
    WOKEN,
    JournalMessage(entries=[]),
    JOURNAL,
    COLLAPSED,
]
CLIENT = [
    PlayerMoveMessage(position=Position(x=14, y=12.25)),
    PlayerMoveMessage(position=Position(x=10, y=11.5, map="coffee_shop")),
    PlayerMoveMessage(position=Position(x=20.37, y=12.6, map="high_street")),
    PlayerSayMessage(text="Hello!", target="mei"),
    WatchNpcMessage(npc_id="mei"),
    WatchNpcMessage(npc_id=None),
    ListNewsMessage(),
    ReadNewsMessage(news_id=ARTICLE.news_id),
    ListWorksMessage(),
    ReadWorkMessage(work_id=POEM.work_id),
    EatMessage(item="noodles"),
    EatMessage(item=None),
    PickUpMessage(),
]


def validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_FILE.read_text()))


@pytest.mark.parametrize("message", SERVER, ids=lambda m: m.type)
def test_server_message_round_trips(message: Any) -> None:
    assert server_messages.validate_json(message.model_dump_json()) == message


@pytest.mark.parametrize("message", CLIENT, ids=lambda m: m.type)
def test_client_message_round_trips(message: Any) -> None:
    assert client_messages.validate_json(message.model_dump_json()) == message


@pytest.mark.parametrize("message", SERVER + CLIENT, ids=lambda m: m.type)
def test_exported_schema_accepts_message(message: Any) -> None:
    validator().validate(json.loads(message.model_dump_json()))


def test_messages_carry_their_type() -> None:
    assert json.loads(SERVER[1].model_dump_json()) == {
        "type": "entity_moved",
        "entity_id": "mei",
        "position": {"x": 4.5, "y": 6.0, "map": "village"},
        "pose": "standing",
        "facing": "south_east",
    }


def test_positions_say_which_map_they_are_on() -> None:
    assert json.loads(SERVER[2].model_dump_json())["position"] == {
        "x": 10.0,
        "y": 12.0,
        "map": "coffee_shop",
    }


def test_a_client_that_sends_no_map_stays_on_the_village() -> None:
    data = {"type": "player_move", "position": {"x": 14, "y": 12.5}}

    validator().validate(data)
    assert client_messages.validate_python(data).position.map == "village"


def test_the_exported_position_has_a_map_but_does_not_require_it() -> None:
    position = json.loads(SCHEMA_FILE.read_text())["$defs"]["Position"]

    assert list(position["properties"]) == ["x", "y", "map"]
    assert position["required"] == ["x", "y"]


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_a_position_schema_never_requires_a_map(mode: JsonSchemaMode) -> None:
    in_messages = TypeAdapter(Message).json_schema(mode=mode)["$defs"]["Position"]

    assert Position.model_json_schema(mode=mode)["required"] == ["x", "y"]
    assert in_messages["required"] == ["x", "y"]


def test_snapshot_entities_carry_their_map() -> None:
    entities = json.loads(SNAPSHOT.model_dump_json())["entities"]

    assert {entity["position"]["map"] for entity in entities} == {"village"}


def test_snapshot_entities_carry_their_pose_and_facing() -> None:
    entities = json.loads(SEATED.model_dump_json())["entities"]

    assert [(e["id"], e["pose"], e["facing"]) for e in entities] == [
        ("mei", "sitting", "west"),
        ("suki", "standing", "south_east"),
        ("viktor", "standing", "south_east"),
        ("player", "standing", "south_east"),
    ]


def test_moves_carry_a_pose_and_facing() -> None:
    message = json.loads(LOOKING.model_dump_json())

    assert (message["pose"], message["facing"]) == ("looking", "north")


@pytest.mark.parametrize(
    ("message", "pose"), [(CLIMBING, "climbing"), (RIDING, "riding")], ids=["climbing", "riding"]
)
def test_moves_can_climb_or_ride(message: EntityMovedMessage, pose: str) -> None:
    assert json.loads(message.model_dump_json())["pose"] == pose
    assert pose in json.loads(SCHEMA_FILE.read_text())["$defs"]["Pose"]["enum"]


@pytest.mark.parametrize(
    "data",
    [
        {"type": "entity_moved", "entity_id": "mei", "position": {"x": 4, "y": 6}},
        {
            "type": "snapshot",
            "time": "2026-03-14T09:10:03Z",
            "map_id": "village",
            "entities": [{"id": "mei", "kind": "npc", "name": "Mei", "position": {"x": 4, "y": 6}}],
            "conversations": [],
        },
    ],
    ids=["entity_moved", "snapshot"],
)
def test_without_a_pose_or_facing_they_stand_facing_south_east(data: dict[str, Any]) -> None:
    validator().validate(data)
    message = server_messages.validate_python(data)
    entity = message.entities[0] if message.type == "snapshot" else message

    assert (entity.pose, entity.facing) == (Pose.STANDING, Facing.SOUTH_EAST)


@pytest.mark.parametrize("model", ["Entity", "EntityMovedMessage"])
def test_the_exported_pose_and_facing_are_not_required(model: str) -> None:
    schema = json.loads(SCHEMA_FILE.read_text())["$defs"][model]

    assert schema["properties"]["pose"] == {"$ref": "#/$defs/Pose"}
    assert schema["properties"]["facing"] == {"$ref": "#/$defs/Facing"}
    assert not {"pose", "facing"} & set(schema["required"])


@pytest.mark.parametrize(
    "update",
    [{"pose": "dancing"}, {"pose": None}, {"facing": "down_right"}, {"facing": "up"}],
)
def test_rejects_poses_and_facings_outside_the_set(update: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        server_messages.validate_python(LOOKING.model_dump() | update)


def test_the_clock_carries_sim_time_and_speed() -> None:
    assert json.loads(CLOCK.model_dump_json()) == {
        "type": "clock",
        "time": "2026-03-14T09:10:03Z",
        "speed": 60.0,
    }


@pytest.mark.parametrize("speed", [0, -1])
def test_the_clock_never_stops_or_runs_backwards(speed: float) -> None:
    with pytest.raises(ValidationError):
        ClockMessage(time=SNAPSHOT.time, speed=speed)


def test_stopping_watching_sends_a_null_npc_id() -> None:
    assert json.loads(WatchNpcMessage(npc_id=None).model_dump_json()) == {
        "type": "watch_npc",
        "npc_id": None,
    }


def test_news_lists_every_field_of_each_article() -> None:
    assert json.loads(NewsMessage(articles=[ARTICLE]).model_dump_json()) == {
        "type": "news",
        "articles": [
            {
                "news_id": "https://bigthink.com/?p=900101",
                "title": "Drones to be regulated",
                "source": "Big Think",
                "summary": "The council votes on drone rules.",
                "url": "https://bigthink.com/drones",
                "read": False,
            }
        ],
    }


def test_a_long_summary_follows_the_short_one() -> None:
    article = json.loads(SUMMARISED.model_dump_json())
    keys = list(article)

    assert article["long_summary"] == LONG_SUMMARY
    assert keys[keys.index("summary") + 1] == "long_summary"


def test_the_exported_article_allows_but_does_not_require_a_long_summary() -> None:
    article = json.loads(SCHEMA_FILE.read_text())["$defs"]["NewsArticle"]

    assert "long_summary" in article["properties"]
    assert "long_summary" not in article["required"]


@pytest.mark.parametrize(
    ("long_summary", "match"),
    [("", "at least 1 character"), ("x" * 4001, "at most 4000 characters")],
)
def test_long_summaries_are_not_empty_or_too_long(long_summary: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        NewsArticle.model_validate(ARTICLE.model_dump() | {"long_summary": long_summary})


def test_works_lists_every_field_of_each_work() -> None:
    assert json.loads(WorksMessage(works=[POEM]).model_dump_json()) == {
        "type": "works",
        "works": [
            {
                "work_id": "work_1",
                "title": "The Footbridge",
                "artist": {"id": "viktor", "name": "Viktor Petrov"},
                "form": "plain verse about old bridges",
                "text": "They built it for a hundred years.\nThe arch has held for ninety-one.",
                "statement": "Things last when people look after them.",
                "created": "2026-03-14T08:40:00Z",
                "read": False,
            }
        ],
        "notices": [],
    }


def test_works_lists_every_field_of_each_notice() -> None:
    message = WorksMessage(works=[], notices=[NOTICE])

    assert json.loads(message.model_dump_json())["notices"] == [
        {
            "notice_id": "notice_1",
            "title": "Two-for-one flat whites",
            "text": "All afternoon, while the oat milk lasts.",
            "poster": {"id": "mirela", "name": "Mirela Popescu"},
            "created": "2026-03-14T09:00:00Z",
        }
    ]


def test_murals_lists_every_wall_with_its_mural_or_null() -> None:
    assert json.loads(MURALS.model_dump_json()) == {
        "type": "murals",
        "walls": [
            {
                "id": "square_north",
                "x": 12,
                "y": 8,
                "width": 4,
                "face": "south",
                "bottom": 0.0,
                "top": 1.0,
                "mural": {
                    "work_id": "work_2",
                    "title": "Who Owns the Sky",
                    "artist": {"id": "suki", "name": "Suki Tanaka"},
                    "statement": "The sky was the one place nobody filled with forms.",
                    "image": "/api/works/work_2.png",
                },
            },
            {
                "id": "park_east",
                "x": 30,
                "y": 14,
                "width": 3,
                "face": "east",
                "bottom": 0.2,
                "top": 2.0,
                "mural": None,
            },
        ],
    }


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"face": "north"}, "face"),
        ({"width": 0}, "width"),
        ({"x": -1}, "x"),
        ({"bottom": -0.5}, "bottom"),
        ({"top": 0}, "top must be above bottom"),
        ({"id": "Square North"}, "String should match pattern"),
        ({"map": ""}, "at least 1 character"),
    ],
)
def test_rejects_invalid_walls(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Wall.model_validate(SQUARE_WALL.model_dump() | update)


def test_a_wall_without_a_map_is_on_the_village_and_dumps_without_one() -> None:
    wall = SQUARE_WALL.model_dump()

    assert "map" not in wall
    assert Wall.model_validate(wall).map == "village"
    assert "map" not in json.loads(Wall.model_validate(wall | {"map": "village"}).model_dump_json())


def test_a_wall_off_the_village_says_which_map_after_its_id() -> None:
    wall = json.loads(STREET_WALL.model_dump_json())

    assert wall["map"] == "market_street"
    assert list(wall)[:3] == ["id", "map", "x"]
    assert Wall.model_validate(wall) == STREET_WALL


def test_the_exported_wall_has_a_map_but_does_not_require_it() -> None:
    wall = json.loads(SCHEMA_FILE.read_text())["$defs"]["Wall"]

    assert "map" in wall["properties"]
    assert "map" not in wall["required"]


def test_paintings_lists_every_frame_with_its_painting_or_null() -> None:
    assert json.loads(PAINTINGS.model_dump_json()) == {
        "type": "paintings",
        "frames": [
            {
                "id": "painting_1",
                "map": "gallery",
                "painting": {
                    "work_id": "work_4",
                    "title": "Low Tide, Six O'Clock",
                    "artist": {"id": "mei", "name": "Mei Lin"},
                    "statement": "The mud flats are the only time the river slows down enough "
                    "to look at.",
                    "image": "/api/gallery/work_4.png",
                },
            },
            {"id": "painting_2", "map": "gallery", "painting": None},
        ],
    }


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"id": "Painting 1"}, "String should match pattern"),
        ({"map": ""}, "at least 1 character"),
        ({"painting": {"work_id": "work_4"}}, "Field required"),
    ],
)
def test_rejects_invalid_frames(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Frame.model_validate(FIRST_FRAME.model_dump() | update)


def test_an_empty_frame_says_so_with_null() -> None:
    frame = FIRST_FRAME.model_dump()
    del frame["painting"]

    with pytest.raises(ValidationError, match="painting\n  Field required"):
        Frame.model_validate(frame)


def test_player_state_has_their_money_items_body_and_hunger() -> None:
    assert json.loads(DELVING.model_dump_json()) == {
        "type": "player_state",
        "player": {
            "money": 120.0,
            "items": [
                {
                    "id": "lamp",
                    "kind": "lamp",
                    "name": "Lamp",
                    "weight": 1.0,
                    "charge": 0.35,
                    "on": True,
                },
                {
                    "id": "copper_wire",
                    "kind": "salvage",
                    "name": "Copper wire",
                    "weight": 1.5,
                    "charge": None,
                    "on": None,
                },
                {
                    "id": "noodles",
                    "kind": "food",
                    "name": "Noodles",
                    "weight": 0.5,
                    "charge": None,
                    "on": None,
                },
            ],
            "carry_limit": 10.0,
            "body": {
                "legs": "hydraulic_legs",
                "vertebra": "present",
                "left_eye": "present",
                "right_eye": "infrared_eye",
                "left_kidney": "sold",
                "right_kidney": "present",
            },
            "hunger": 0.55,
        },
    }


def keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in keys(item)}
    return set()


@pytest.mark.parametrize("message", [STARTING, DELVING], ids=["starting", "delving"])
def test_player_state_never_carries_humanity(message: PlayerStateMessage) -> None:
    assert 0 < message.player.humanity <= 1
    assert "humanity" not in keys(json.loads(message.model_dump_json()))


def test_the_exported_protocol_has_no_humanity() -> None:
    schema = json.loads(SCHEMA_FILE.read_text())

    assert "humanity" not in {
        name for model in schema["$defs"].values() for name in model.get("properties", {})
    }


def test_rejects_a_player_state_with_humanity() -> None:
    data = json.loads(STARTING.model_dump_json())
    data["player"]["humanity"] = 1.0

    assert not validator().is_valid(data)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        server_messages.validate_python(data)


def test_player_state_says_what_meal_is_on_offer_where_they_stand() -> None:
    data = json.loads(AT_THE_NOODLE_BAR.model_dump_json())

    assert data == json.loads(DELVING.model_dump_json()) | {
        "meal": {"place": "noodle_bar", "name": "Golden Bowl Noodles", "price": 10.0}
    }


@pytest.mark.parametrize("message", [STARTING, DELVING], ids=["starting", "delving"])
def test_player_state_without_a_meal_or_piles_dumps_as_before(message: PlayerStateMessage) -> None:
    data = json.loads(message.model_dump_json())

    assert set(data) == {"type", "player"}
    assert set(data["player"]) == {"money", "items", "carry_limit", "body", "hunger"}


def test_player_state_has_what_they_left_where_they_collapsed() -> None:
    player = json.loads(WOKEN.model_dump_json())["player"]

    assert player["items"] == []
    assert player["left"] == [
        {
            "at": {"map": "kapok_walk", "x": 12, "y": 15},
            "items": [json.loads(lamp().model_dump_json())],
        }
    ]


def test_the_exported_player_state_has_a_meal_and_piles_but_does_not_require_them() -> None:
    defs = json.loads(SCHEMA_FILE.read_text())["$defs"]

    assert "meal" in defs["PlayerStateMessage"]["properties"]
    assert "meal" not in defs["PlayerStateMessage"]["required"]
    assert "left" in defs["Player"]["properties"]
    assert "left" not in defs["Player"]["required"]


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"price": -1}, "greater than or equal to 0"),
        ({"price": float("inf")}, "finite number"),
        ({"name": ""}, "at least 1 character"),
        ({"place": "Noodle bar"}, "String should match pattern"),
    ],
)
def test_rejects_invalid_meals(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Meal.model_validate(NOODLES.model_dump() | update)


def test_a_collapse_says_where_they_wake() -> None:
    assert json.loads(COLLAPSED.model_dump_json()) == {
        "type": "player_collapsed",
        "position": {"x": 13.0, "y": 2.0, "map": "maker_space_floor_0"},
    }


@pytest.mark.parametrize(
    ("message", "data"),
    [
        (EatMessage(item="noodles"), {"type": "eat", "item": "noodles"}),
        (EatMessage(item=None), {"type": "eat", "item": None}),
        (PickUpMessage(), {"type": "pick_up"}),
    ],
    ids=["item", "meal", "pick_up"],
)
def test_eating_and_picking_up_go_from_client_to_server(message: Any, data: dict[str, Any]) -> None:
    assert json.loads(message.model_dump_json()) == data
    assert client_messages.validate_python(data) == message
    with pytest.raises(ValidationError):
        server_messages.validate_python(data)


def test_a_collapse_goes_only_from_server_to_client() -> None:
    data = json.loads(COLLAPSED.model_dump_json())

    assert server_messages.validate_python(data) == COLLAPSED
    with pytest.raises(ValidationError):
        client_messages.validate_python(data)


def test_a_flushed_line_says_so() -> None:
    message = LineMessage(line=CONVERSATION.lines[-1], voiced=True, flushed=True)

    assert json.loads(message.model_dump_json()) == {
        "type": "line",
        "line": json.loads(CONVERSATION.lines[-1].model_dump_json()),
        "voiced": True,
        "flushed": True,
    }


@pytest.mark.parametrize(
    "message",
    [
        LineMessage(line=CONVERSATION.lines[-1], voiced=True),
        LineMessage(line=CONVERSATION.lines[-1], voiced=True, flushed=False),
    ],
    ids=["unset", "false"],
)
def test_a_line_without_a_flush_dumps_as_before(message: LineMessage) -> None:
    assert json.loads(message.model_dump_json()) == {
        "type": "line",
        "line": json.loads(CONVERSATION.lines[-1].model_dump_json()),
        "voiced": True,
    }


def test_a_line_message_without_flushed_is_no_flush() -> None:
    line = json.loads(CONVERSATION.lines[-1].model_dump_json())
    data = {"type": "line", "line": line, "voiced": False}

    validator().validate(data)
    assert server_messages.validate_python(data).flushed is False


def test_the_exported_line_message_has_flushed_but_does_not_require_it() -> None:
    message = json.loads(SCHEMA_FILE.read_text())["$defs"]["LineMessage"]

    assert message["properties"]["flushed"]["type"] == "boolean"
    assert "flushed" not in message["required"]


def test_the_journal_has_every_entry_in_the_order_learned_with_its_open_leads() -> None:
    assert json.loads(JOURNAL.model_dump_json()) == {
        "type": "journal",
        "entries": [
            {
                "fact_id": "notes",
                "text": "Aris wrote that R. came about the machines again, and said he'd make her "
                "regret it.",
                "source": {"kind": "clue", "id": "aris_notes", "name": "Aris's notes"},
                "learned": "2026-03-14T10:05:00Z",
                "flushed": None,
                "leads": [
                    {"fact_id": "motive", "text": "Who's R.? Mirela knows everyone's business."}
                ],
            },
            {
                "fact_id": "attack",
                "text": "Raymond says he was at home going over the accounts all night.",
                "source": {"kind": "resident", "id": "raymond", "name": "Raymond"},
                "learned": "2026-03-17T14:00:00Z",
                "flushed": True,
                "leads": [],
            },
        ],
    }


def test_the_journal_goes_only_from_server_to_client() -> None:
    data = json.loads(JOURNAL.model_dump_json())

    assert server_messages.validate_python(data) == JOURNAL
    with pytest.raises(ValidationError):
        client_messages.validate_python(data)


def test_the_exported_journal_entry_requires_every_field() -> None:
    entry = json.loads(SCHEMA_FILE.read_text())["$defs"]["JournalEntry"]

    assert entry["required"] == ["fact_id", "text", "source", "learned", "flushed", "leads"]


def test_rejects_a_flush_on_a_clue_in_the_journal() -> None:
    data = json.loads(JOURNAL.model_dump_json())
    data["entries"][0]["flushed"] = False

    with pytest.raises(ValidationError, match="only a resident can flush"):
        server_messages.validate_python(data)


def test_timestamps_are_utc() -> None:
    sydney = datetime(2026, 3, 14, 20, 10, 3, tzinfo=timezone(timedelta(hours=11)))

    assert json.loads(fixture_snapshot(sydney).model_dump_json())["time"] == "2026-03-14T09:10:03Z"


@pytest.mark.parametrize(
    "data",
    [
        {"type": "snapshot"},
        {"type": "player_move", "position": {"x": 1, "y": 2}, "speed": 3},
        {"type": "player_move", "position": {"x": 1, "y": 2, "map": ""}},
        {"type": "player_move", "position": {"x": 1, "y": 2, "map": None}},
        {"type": "player_say", "text": "", "target": "mei"},
        {"type": "player_say", "text": "Hi", "target": "Mei"},
        {"type": "watch_npc"},
        {"type": "watch_npc", "npc_id": "Mei"},
        {"type": "list_news", "news_id": "n1"},
        {"type": "read_news"},
        {"type": "read_news", "news_id": ""},
        {"type": "list_works", "work_id": "work_1"},
        {"type": "read_work"},
        {"type": "read_work", "work_id": ""},
        {"type": "eat"},
        {"type": "eat", "item": "Noodles"},
        {"type": "pick_up", "item": "lamp"},
    ],
)
def test_rejects_invalid_client_messages(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        client_messages.validate_python(data)


def test_fixture_snapshot_has_everyone_and_only_active_conversations() -> None:
    assert [(e.id, e.kind) for e in SNAPSHOT.entities] == [
        ("mei", "npc"),
        ("suki", "npc"),
        ("viktor", "npc"),
        ("player", "player"),
    ]
    assert SNAPSHOT.entities[0].position == Position(x=3, y=11)
    assert [c.id for c in SNAPSHOT.conversations] == ["conv_2"]
