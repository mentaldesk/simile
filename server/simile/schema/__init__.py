from simile.schema.common import PLAYER_ID, Colour, Id, Key, Model, Signed, Timestamp, Unit
from simile.schema.conversation import Conversation, Line
from simile.schema.news import NewsItem
from simile.schema.npc import Accessory, Appearance, Build, CoreValue, HairStyle, Npc, Voice
from simile.schema.social import (
    Aspect,
    Baseline,
    Flag,
    FlagKind,
    InteractionEvent,
    Memory,
    MemoryKind,
    Relationship,
)
from simile.schema.world import Location, LocationKind, Tile, TileArea

MODELS: tuple[type[Model], ...] = (
    Npc,
    Appearance,
    Voice,
    Relationship,
    InteractionEvent,
    Flag,
    Memory,
    NewsItem,
    Location,
    Conversation,
    Line,
)

__all__ = [
    "MODELS",
    "PLAYER_ID",
    "Accessory",
    "Appearance",
    "Aspect",
    "Baseline",
    "Build",
    "Colour",
    "Conversation",
    "CoreValue",
    "Flag",
    "FlagKind",
    "HairStyle",
    "Id",
    "InteractionEvent",
    "Key",
    "Line",
    "Location",
    "LocationKind",
    "Memory",
    "MemoryKind",
    "Model",
    "NewsItem",
    "Npc",
    "Relationship",
    "Signed",
    "Tile",
    "TileArea",
    "Timestamp",
    "Unit",
    "Voice",
]
