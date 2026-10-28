import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError
from pydantic.json_schema import JsonSchemaMode

from simile.protocol import (
    Artist,
    Buyer,
    BuyMessage,
    ClockMessage,
    ConversationEndedMessage,
    ConversationStartedMessage,
    Creature,
    CreatureGoneMessage,
    CreatureMovedMessage,
    EatMessage,
    EntityMovedMessage,
    Face,
    FitMessage,
    Fitting,
    Frame,
    JournalMessage,
    LampMessage,
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
    Offer,
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
    SellMessage,
    SellPartMessage,
    SellRecipeMessage,
    Shut,
    ShutReason,
    Treatment,
    TreatMessage,
    Vital,
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
    CreatureKind,
    CreatureState,
    Effect,
    EffectKind,
    Facing,
    Item,
    ItemKind,
    JournalEntry,
    Lead,
    MapTile,
    Mind,
    Pile,
    Player,
    Pose,
    Recipe,
    Sale,
    Source,
    SourceKind,
    lamp,
)

CREATURE_FIGURES = Path(__file__).parents[3] / "content" / "creatures"
CREATURES = TypeAdapter(list[Creature]).validate_json(
    (Path(__file__).parent / "creatures.json").read_bytes()
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
        body=Body(legs=Bionic.BIONIC_LEGS, right_eye=Bionic.INFRARED_EYE, left_kidney="sold"),
        hunger=0.55,
    )
)

NOODLES = Meal(place="noodle_bar", name="Golden Bowl Noodles", price=10)
AT_THE_NOODLE_BAR = DELVING.model_copy(update={"meal": NOODLES})
NOODLES_SHUT = Shut(
    place="noodle_bar",
    name="Golden Bowl Noodles",
    reason=ShutReason.CLOSED,
    opens=datetime(2026, 3, 17, 11, tzinfo=UTC),
)
AT_THE_SHUT_NOODLE_BAR = DELVING.model_copy(update={"shut": NOODLES_SHUT})
AT_A_SHOP_NOBODY_KEEPS = DELVING.model_copy(
    update={"shut": NOODLES_SHUT.model_copy(update={"opens": None})}
)
WIRE = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)
WOKEN = PlayerStateMessage(
    player=Player(
        hunger=0.75,
        left=[Pile(at=MapTile(map="kapok_walk", x=12, y=15), items=[WIRE])],
    ),
    meal=Meal(place="maker_space", name="home", price=0),
)
COLLAPSED = PlayerCollapsedMessage(position=Position(x=13, y=2, map="maker_space_floor_0"))
SCRAP_TRADER = Buyer(place="scrap_stall", name="The scrap trader", prices={"copper_wire": 6})
AT_THE_SCRAP_STALL = DELVING.model_copy(update={"buyer": SCRAP_TRADER})
LEGS = Fitting(bionic=Bionic.BIONIC_LEGS, name="Bionic legs", price=80, parts=["legs"])
EYE = Fitting(
    bionic=Bionic.INFRARED_EYE, name="Infrared eye", price=200, parts=["left_eye", "right_eye"]
)
DOCTOR = Buyer(
    place="clinic",
    name="The Clinic",
    prices={},
    parts={"left_kidney": 100},
    fittings=[LEGS, EYE],
)
AT_THE_CLINIC = STARTING.model_copy(update={"buyer": DOCTOR})
CELL_RECIPE = Recipe(
    bionic=Bionic.POWER_CELL, name="Power cell", parts={"lithium_cell": 2}, credits=90
)
JACK_RECIPE = Recipe(
    bionic=Bionic.DATAJACK,
    name="Datajack",
    parts={"copper_wire": 3, "usb_c_connector": 1},
    credits=100,
    after=[Bionic.POWER_CELL],
)
KNOWING = PlayerStateMessage(
    player=Player(
        body=Body(stomach=Bionic.POWER_CELL, legs=Bionic.BIONIC_LEGS, feet=Bionic.SPRING_FEET),
        mind=Mind(recipes=[Bionic.POWER_CELL, Bionic.DATAJACK], sold=[Bionic.POWER_CELL]),
    ),
    recipes=[CELL_RECIPE, JACK_RECIPE],
)
SELLING_RECIPES = KNOWING.model_copy(
    update={"buyer": DOCTOR.model_copy(update={"recipes": {Bionic.DATAJACK: 40}})}
)
USB_C = Item(id="usb_c_connector", kind=ItemKind.PART, name="USB-C connector", weight=0.1)
HURT = PlayerStateMessage(
    player=Player(
        body=Body(stomach=Bionic.POWER_CELL),
        power=0.65,
        health=0.5,
        effects=[
            Effect(
                kind=EffectKind.RAT_BITE,
                strength=0.2,
                fades=0.05,
                since=datetime(2026, 3, 15, 11, 20, tzinfo=UTC),
            ),
            Effect(
                kind=EffectKind.INFECTION,
                strength=0.6,
                fades=None,
                since=datetime(2026, 3, 15, 9, tzinfo=UTC),
            ),
        ],
        sales=[Sale(item=USB_C, place="scrap_stall", price=20)],
    ),
)
BUYING_BACK = HURT.model_copy(
    update={
        "buyer": SCRAP_TRADER.model_copy(update={"stock": [Offer(item=USB_C, price=40)]}),
    }
)
PATCH_UP = Treatment(effect=None, name="Patch up", price=30)
TREAT_INFECTION = Treatment(effect=EffectKind.INFECTION, name="Treat the infection", price=45)
TREATING = HURT.model_copy(
    update={
        "buyer": DOCTOR.model_copy(
            update={"fittings": [], "parts": {}, "treatments": [PATCH_UP, TREAT_INFECTION]}
        )
    }
)
SEARCHED = PlayerStateMessage(
    player=Player(
        items=[lamp(), USB_C],
        mind=Mind(recipes=[Bionic.DATAJACK]),
        searched=["aris_bench", "maker_space_drawers"],
    ),
    recipes=[JACK_RECIPE],
)
DRAINED = PlayerCollapsedMessage(position=Position(x=4, y=9, map="home"), cause=Vital.POWER)
SERVO = Item(id="servo_motor", kind=ItemKind.SALVAGE, name="Servo motor", weight=3)
RATION_PACK = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)
IN_THE_METRO = STARTING.model_copy(
    update={
        "piles": [
            Pile(at=MapTile(map="metro", x=8, y=7), items=[], money=25),
            Pile(at=MapTile(map="metro", x=108, y=12), items=[SERVO]),
            Pile(at=MapTile(map="metro", x=86, y=8), items=[RATION_PACK]),
        ]
    }
)

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
IN_THE_SEWERS = SNAPSHOT.model_copy(update={"creatures": CREATURES})
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
    AT_THE_SCRAP_STALL,
    AT_THE_CLINIC,
    IN_THE_METRO,
    KNOWING,
    SELLING_RECIPES,
    AT_THE_SHUT_NOODLE_BAR,
    AT_A_SHOP_NOBODY_KEEPS,
    HURT,
    BUYING_BACK,
    TREATING,
    SEARCHED,
    JournalMessage(entries=[]),
    JOURNAL,
    COLLAPSED,
    DRAINED,
    IN_THE_SEWERS,
    *(CreatureMovedMessage(creature=creature) for creature in CREATURES),
    CreatureGoneMessage(creature_id="rat_2"),
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
    SellMessage(item="copper_wire"),
    SellMessage(item=None),
    LampMessage(on=True),
    LampMessage(on=False),
    SellPartMessage(part="left_kidney"),
    FitMessage(bionic=Bionic.INFRARED_EYE, part="right_eye"),
    FitMessage(bionic=Bionic.POWER_CELL, part="stomach"),
    SellRecipeMessage(recipe=Bionic.DATAJACK),
    BuyMessage(item="usb_c_connector"),
    TreatMessage(effect=None),
    TreatMessage(effect=EffectKind.INFECTION),
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
                "legs": "bionic_legs",
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


def test_player_state_says_when_the_shop_they_stand_in_next_serves() -> None:
    data = json.loads(AT_THE_SHUT_NOODLE_BAR.model_dump_json())

    assert data == json.loads(DELVING.model_dump_json()) | {
        "shut": {
            "place": "noodle_bar",
            "name": "Golden Bowl Noodles",
            "reason": "closed",
            "opens": "2026-03-17T11:00:00Z",
        }
    }
    assert {reason.value for reason in ShutReason} == {"closed", "sold_out"}


def test_a_shop_without_a_keeper_has_no_opening() -> None:
    shut = json.loads(AT_A_SHOP_NOBODY_KEEPS.model_dump_json())["shut"]

    assert (shut["reason"], shut["opens"]) == ("closed", None)


def test_player_state_has_a_meal_or_a_shut_shop_not_both() -> None:
    with pytest.raises(ValidationError, match="not both"):
        PlayerStateMessage(player=Player(), meal=NOODLES, shut=NOODLES_SHUT)


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"name": ""}, "at least 1 character"),
        ({"place": "Noodle bar"}, "String should match pattern"),
        ({"reason": "busy"}, "Input should be 'closed' or 'sold_out'"),
        ({"opens": "2026-03-17T11:00:00"}, "timezone info"),
    ],
)
def test_rejects_invalid_shut_shops(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Shut.model_validate(NOODLES_SHUT.model_dump() | update)


@pytest.mark.parametrize("message", [STARTING, DELVING], ids=["starting", "delving"])
def test_player_state_without_a_meal_buyer_or_piles_dumps_as_before(
    message: PlayerStateMessage,
) -> None:
    data = json.loads(message.model_dump_json())

    assert set(data) == {"type", "player"}
    assert set(data["player"]) == {"money", "items", "carry_limit", "body", "hunger"}


def test_player_state_has_the_recipes_they_know_in_full() -> None:
    data = json.loads(KNOWING.model_dump_json())

    body = data["player"]["body"]
    assert (body["stomach"], body["feet"]) == ("power_cell", "spring_feet")
    assert data["player"]["mind"] == {
        "recipes": ["power_cell", "datajack"],
        "sold": ["power_cell"],
    }
    assert data["recipes"] == [
        {
            "bionic": "power_cell",
            "name": "Power cell",
            "parts": {"lithium_cell": 2},
            "credits": 90.0,
            "replaces": ["stomach"],
            "after": [],
        },
        {
            "bionic": "datajack",
            "name": "Datajack",
            "parts": {"copper_wire": 3, "usb_c_connector": 1},
            "credits": 100.0,
            "replaces": ["vertebra"],
            "after": ["power_cell"],
        },
    ]


@pytest.mark.parametrize(
    "recipes", [[], [JACK_RECIPE], [JACK_RECIPE, CELL_RECIPE]], ids=["none", "one", "out_of_order"]
)
def test_rejects_a_player_state_without_each_recipe_they_know(recipes: list[Recipe]) -> None:
    with pytest.raises(ValidationError, match="each recipe they know, in order"):
        PlayerStateMessage(player=KNOWING.player, recipes=recipes)


def test_player_state_says_which_recipes_the_clinic_would_buy() -> None:
    data = json.loads(SELLING_RECIPES.model_dump_json())

    assert data["buyer"]["recipes"] == {"datajack": 40.0}
    recipes = json.loads(SCHEMA_FILE.read_text())["$defs"]["Buyer"]["properties"]["recipes"]
    assert recipes["propertyNames"] == {"$ref": "#/$defs/Bionic"}


def test_player_state_has_their_vitals_and_effects() -> None:
    player = json.loads(HURT.model_dump_json())["player"]

    assert (player["hunger"], player["power"], player["health"]) == (0.0, 0.65, 0.5)
    assert player["effects"] == [
        {"kind": "rat_bite", "strength": 0.2, "fades": 0.05, "since": "2026-03-15T11:20:00Z"},
        {"kind": "infection", "strength": 0.6, "fades": None, "since": "2026-03-15T09:00:00Z"},
    ]


def test_player_state_says_what_the_buyer_sells_back_and_for_what() -> None:
    data = json.loads(BUYING_BACK.model_dump_json())

    assert data["player"]["sales"] == [
        {"item": USB_C.model_dump(mode="json"), "place": "scrap_stall", "price": 20.0}
    ]
    assert data["buyer"]["stock"] == [{"item": USB_C.model_dump(mode="json"), "price": 40.0}]


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"price": -1}, "greater than or equal to 0"),
        ({"price": float("nan")}, "finite number"),
        ({"item": None}, "valid dictionary"),
    ],
)
def test_rejects_invalid_offers(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Offer.model_validate(Offer(item=USB_C, price=40).model_dump() | update)


def test_player_state_has_what_they_left_where_they_collapsed() -> None:
    player = json.loads(WOKEN.model_dump_json())["player"]

    assert player["items"] == [json.loads(lamp().model_dump_json())]
    assert player["left"] == [
        {
            "at": {"map": "kapok_walk", "x": 12, "y": 15},
            "items": [json.loads(WIRE.model_dump_json())],
        }
    ]


@pytest.mark.parametrize(
    ("model", "field"),
    [
        ("PlayerStateMessage", "meal"),
        ("PlayerStateMessage", "shut"),
        ("PlayerStateMessage", "buyer"),
        ("PlayerStateMessage", "piles"),
        ("PlayerStateMessage", "recipes"),
        ("Buyer", "parts"),
        ("Buyer", "fittings"),
        ("Buyer", "recipes"),
        ("Buyer", "stock"),
        ("Buyer", "treatments"),
        ("SnapshotMessage", "creatures"),
        ("Player", "searched"),
        ("Player", "power"),
        ("Player", "health"),
        ("Player", "effects"),
        ("Player", "sales"),
        ("Player", "left"),
        ("Player", "taken"),
        ("Player", "mind"),
        ("Body", "stomach"),
        ("Body", "feet"),
        ("Mind", "sold"),
        ("Pile", "money"),
    ],
)
def test_the_exported_protocol_has_fields_it_does_not_require(model: str, field: str) -> None:
    defs = json.loads(SCHEMA_FILE.read_text())["$defs"]

    assert field in defs[model]["properties"]
    assert field not in defs[model]["required"]


def test_player_state_says_who_buys_where_they_stand_and_for_what() -> None:
    data = json.loads(AT_THE_SCRAP_STALL.model_dump_json())

    assert data == json.loads(DELVING.model_dump_json()) | {
        "buyer": {
            "place": "scrap_stall",
            "name": "The scrap trader",
            "prices": {"copper_wire": 6.0},
        }
    }


def test_player_state_says_what_the_clinic_buys_of_their_body_and_fits() -> None:
    data = json.loads(AT_THE_CLINIC.model_dump_json())

    assert data == json.loads(STARTING.model_dump_json()) | {
        "buyer": {
            "place": "clinic",
            "name": "The Clinic",
            "prices": {},
            "parts": {"left_kidney": 100.0},
            "fittings": [
                {
                    "bionic": "bionic_legs",
                    "name": "Bionic legs",
                    "price": 80.0,
                    "parts": ["legs"],
                },
                {
                    "bionic": "infrared_eye",
                    "name": "Infrared eye",
                    "price": 200.0,
                    "parts": ["left_eye", "right_eye"],
                },
            ],
        }
    }


def test_the_exported_buyer_buys_only_parts_of_the_body() -> None:
    parts = json.loads(SCHEMA_FILE.read_text())["$defs"]["Buyer"]["properties"]["parts"]

    assert parts["propertyNames"] == {"$ref": "#/$defs/BodyPart"}
    assert not validator().is_valid(
        json.loads(AT_THE_CLINIC.model_dump_json())
        | {"buyer": DOCTOR.model_dump(mode="json") | {"parts": {"tail": 100}}}
    )


def test_a_buyer_that_buys_no_parts_and_fits_nothing_dumps_as_before() -> None:
    buyer = DOCTOR.model_copy(update={"parts": {}, "fittings": []})

    assert set(json.loads(buyer.model_dump_json())) == {"place", "name", "prices"}


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"parts": []}, "at least 1 item"),
        ({"parts": ["tail"]}, "Input should be 'legs'"),
        ({"parts": ("left_kidney",)}, "bionic_legs can't replace left_kidney"),
        (
            {"bionic": "infrared_eye", "parts": ("left_eye", "left_eye")},
            "a fitting names each part once",
        ),
        ({"bionic": "steel_hand"}, "Input should be 'datajack'"),
        ({"price": -1}, "greater than or equal to 0"),
        ({"price": float("nan")}, "finite number"),
        ({"name": ""}, "at least 1 character"),
        ({"parts": ["left_kidney"]}, "bionic_legs can't replace left_kidney"),
        ({"parts": ["legs", "legs"]}, "a fitting names each part once"),
        (
            {"bionic": "infrared_eye", "parts": ["right_eye", "right_eye"]},
            "a fitting names each part once",
        ),
        (
            {"bionic": "datajack", "parts": ["vertebra", "left_eye"]},
            "datajack can't replace left_eye",
        ),
    ],
)
def test_rejects_invalid_fittings(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Fitting.model_validate(LEGS.model_dump() | update)


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"type": "sell_part", "part": "tail"}, "Input should be 'legs'"),
        ({"type": "sell_part"}, "Field required"),
        ({"type": "fit", "bionic": "datajack"}, "Field required"),
        ({"type": "fit", "bionic": "steel_hand", "part": "legs"}, "Input should be"),
    ],
)
def test_rejects_parts_and_fittings_that_are_not_the_bodys(
    data: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        client_messages.validate_python(data)


def test_a_buyer_can_buy_nothing_they_carry() -> None:
    buyer = SCRAP_TRADER.model_copy(update={"prices": {}})

    assert json.loads(buyer.model_dump_json())["prices"] == {}


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"prices": {"copper_wire": -1}}, "greater than or equal to 0"),
        ({"prices": {"copper_wire": float("inf")}}, "finite number"),
        ({"parts": {"left_kidney": -1}}, "greater than or equal to 0"),
        ({"parts": {"tail": 100}}, "Input should be 'legs'"),
        ({"fittings": [LEGS.model_dump(), LEGS.model_dump()]}, "a buyer offers each bionic once"),
        ({"prices": {"": 6}}, "at least 1 character"),
        ({"name": ""}, "at least 1 character"),
        ({"place": "Scrap stall"}, "String should match pattern"),
    ],
)
def test_rejects_invalid_buyers(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Buyer.model_validate(SCRAP_TRADER.model_dump() | update)


def test_player_state_has_what_lies_in_the_world_to_pick_up() -> None:
    data = json.loads(IN_THE_METRO.model_dump_json())

    assert set(data) == {"type", "player", "piles"}
    assert data["piles"] == [
        {"at": {"map": "metro", "x": 8, "y": 7}, "items": [], "money": 25.0},
        {"at": {"map": "metro", "x": 108, "y": 12}, "items": [json.loads(SERVO.model_dump_json())]},
        {
            "at": {"map": "metro", "x": 86, "y": 8},
            "items": [json.loads(RATION_PACK.model_dump_json())],
        },
    ]


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


def test_a_collapse_says_where_they_wake_and_why() -> None:
    assert json.loads(COLLAPSED.model_dump_json()) == {
        "type": "player_collapsed",
        "position": {"x": 13.0, "y": 2.0, "map": "maker_space_floor_0"},
        "cause": "hunger",
    }
    assert json.loads(DRAINED.model_dump_json())["cause"] == "power"
    assert {vital.value for vital in Vital} == {"hunger", "power", "health"}


def test_a_collapse_from_before_its_cause_was_hunger() -> None:
    data = {"type": "player_collapsed", "position": {"x": 13, "y": 2}}

    assert server_messages.validate_python(data).cause is Vital.HUNGER


@pytest.mark.parametrize(
    ("message", "data"),
    [
        (EatMessage(item="noodles"), {"type": "eat", "item": "noodles"}),
        (EatMessage(item=None), {"type": "eat", "item": None}),
        (PickUpMessage(), {"type": "pick_up"}),
        (SellMessage(item="copper_wire"), {"type": "sell", "item": "copper_wire"}),
        (SellMessage(item=None), {"type": "sell", "item": None}),
        (LampMessage(on=True), {"type": "lamp", "on": True}),
        (LampMessage(on=False), {"type": "lamp", "on": False}),
        (SellPartMessage(part="left_kidney"), {"type": "sell_part", "part": "left_kidney"}),
        (
            FitMessage(bionic=Bionic.DATAJACK, part="vertebra"),
            {"type": "fit", "bionic": "datajack", "part": "vertebra"},
        ),
        (
            SellRecipeMessage(recipe=Bionic.DATAJACK),
            {"type": "sell_recipe", "recipe": "datajack"},
        ),
        (BuyMessage(item="usb_c_connector"), {"type": "buy", "item": "usb_c_connector"}),
        (TreatMessage(effect=None), {"type": "treat", "effect": None}),
        (
            TreatMessage(effect=EffectKind.RAT_BITE),
            {"type": "treat", "effect": "rat_bite"},
        ),
    ],
    ids=[
        "item",
        "meal",
        "pick_up",
        "sell_one",
        "sell_all",
        "lamp_on",
        "lamp_off",
        "sell_part",
        "fit",
        "sell_recipe",
        "buy",
        "patch_up",
        "treat",
    ],
)
def test_eating_picking_up_selling_and_the_lamp_go_from_client_to_server(
    message: Any, data: dict[str, Any]
) -> None:
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
        {"type": "sell"},
        {"type": "sell", "item": "Copper wire"},
        {"type": "sell", "item": "copper_wire", "price": 6},
        {"type": "lamp"},
        {"type": "lamp", "on": None},
        {"type": "lamp", "on": "maybe"},
        {"type": "lamp", "on": True, "charge": 1},
        {"type": "buy"},
        {"type": "buy", "item": None},
        {"type": "buy", "item": "USB-C connector"},
        {"type": "buy", "item": "usb_c_connector", "price": 40},
        {"type": "treat"},
        {"type": "treat", "effect": "snake_bite"},
        {"type": "kick", "facing": "east"},
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


def test_the_snapshot_has_every_creature_on_every_map() -> None:
    data = json.loads(IN_THE_SEWERS.model_dump_json())

    assert data["creatures"] == json.loads((Path(__file__).parent / "creatures.json").read_text())
    assert json.loads(SNAPSHOT.model_dump_json())["creatures"] == []


def test_a_snapshot_without_creatures_has_none() -> None:
    data = json.loads(SNAPSHOT.model_dump_json())
    del data["creatures"]

    validator().validate(data)
    assert server_messages.validate_python(data).creatures == []


def test_a_creature_moving_carries_all_of_it_so_a_new_one_can_appear() -> None:
    assert json.loads(CreatureMovedMessage(creature=CREATURES[2]).model_dump_json()) == {
        "type": "creature_moved",
        "creature": {
            "id": "dog_1",
            "kind": "dog",
            "position": {"x": 61.25, "y": 18.0, "map": "sewers"},
            "facing": "east",
            "state": "chasing",
        },
    }
    assert json.loads(CreatureGoneMessage(creature_id="rat_2").model_dump_json()) == {
        "type": "creature_gone",
        "creature_id": "rat_2",
    }


def test_creatures_are_rats_bots_dogs_and_bats_named_as_their_figures() -> None:
    assert [kind.value for kind in CreatureKind] == ["rat", "bot", "dog", "bat"]
    assert [state.value for state in CreatureState] == [
        "idle",
        "moving",
        "chasing",
        "fleeing",
        "attacking",
        "roosting",
        "hurt",
    ]


@pytest.mark.parametrize("kind", list(CreatureKind))
def test_each_kind_of_creature_has_its_figure(kind: CreatureKind) -> None:
    figure = json.loads((CREATURE_FIGURES / f"{kind}.json").read_text())

    assert figure["id"] == kind


def test_creatures_face_right_or_left() -> None:
    defs = json.loads(SCHEMA_FILE.read_text())["$defs"]

    assert defs["SideFacing"]["enum"] == ["east", "west"]
    assert defs["Creature"]["properties"]["facing"] == {"$ref": "#/$defs/SideFacing"}


def test_the_exported_creature_requires_every_field() -> None:
    creature = json.loads(SCHEMA_FILE.read_text())["$defs"]["Creature"]

    assert sorted(creature["required"]) == ["facing", "id", "kind", "position", "state"]


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"state": "roosting"}, "only a bat roosts"),
        ({"kind": "snake"}, "Input should be 'rat'"),
        ({"state": "dead"}, "Input should be 'idle'"),
        ({"facing": "up"}, "Input should be 'east' or 'west'"),
        ({"facing": "north"}, "Input should be 'east' or 'west'"),
        ({"facing": "south_east"}, "Input should be 'east' or 'west'"),
        ({"id": "Rat 1"}, "String should match pattern"),
        ({"health": 0.5}, "Extra inputs"),
    ],
)
def test_rejects_invalid_creatures(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Creature.model_validate(CREATURES[0].model_dump() | update)


def test_creature_messages_go_only_from_server_to_client() -> None:
    for message in (
        CreatureMovedMessage(creature=CREATURES[0]),
        CreatureGoneMessage(creature_id="rat_1"),
    ):
        with pytest.raises(ValidationError):
            client_messages.validate_python(json.loads(message.model_dump_json()))


def test_player_state_says_what_the_clinic_would_treat_and_for_what() -> None:
    buyer = json.loads(TREATING.model_dump_json())["buyer"]

    assert buyer["treatments"] == [
        {"effect": None, "name": "Patch up", "price": 30.0},
        {"effect": "infection", "name": "Treat the infection", "price": 45.0},
    ]
    assert "treatments" not in json.loads(DOCTOR.model_dump_json())


@pytest.mark.parametrize(
    ("update", "match"),
    [
        (
            {"treatments": [PATCH_UP.model_dump(), PATCH_UP.model_dump()]},
            "a buyer offers each treatment once",
        ),
        (
            {"treatments": [TREAT_INFECTION.model_dump(), TREAT_INFECTION.model_dump()]},
            "a buyer offers each treatment once",
        ),
        ({"treatments": [PATCH_UP.model_dump() | {"price": -1}]}, "greater than or equal to 0"),
        ({"treatments": [PATCH_UP.model_dump() | {"name": ""}]}, "at least 1 character"),
        ({"treatments": [PATCH_UP.model_dump() | {"effect": "snake_bite"}]}, "rat_bite"),
        ({"treatments": [{"name": "Patch up", "price": 30}]}, "Field required"),
    ],
)
def test_rejects_invalid_treatments(update: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Buyer.model_validate(DOCTOR.model_dump() | update)


def test_player_state_says_what_they_have_searched() -> None:
    player = json.loads(SEARCHED.model_dump_json())["player"]

    assert player["searched"] == ["aris_bench", "maker_space_drawers"]
    assert "searched" not in json.loads(STARTING.model_dump_json())["player"]
