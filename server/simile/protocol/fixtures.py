from functools import cache
from pathlib import Path

from pydantic import TypeAdapter

from simile.protocol.messages import Entity, EntityKind, Position, SnapshotMessage
from simile.schema import PLAYER_ID, Conversation, Location, Npc

FIXTURES = Path(__file__).parents[2] / "tests" / "fixtures"
MAP_ID = "village"


def standing_at(location: Location) -> Position:
    return Position(x=location.entry.x, y=location.entry.y)


@cache
def fixture_snapshot() -> SnapshotMessage:
    """F2's example world, until the sim has a real one: NPCs at home, the player in the square."""
    locations = {
        location.id: location
        for location in TypeAdapter(list[Location]).validate_json(
            (FIXTURES / "locations.json").read_bytes()
        )
    }
    npcs = [
        Npc.model_validate_json(path.read_bytes())
        for path in sorted((FIXTURES / "npcs").glob("*.json"))
    ]
    conversations = TypeAdapter(list[Conversation]).validate_json(
        (FIXTURES / "conversations.json").read_bytes()
    )
    entities = [
        Entity(
            id=npc.id, kind=EntityKind.NPC, name=npc.name, position=standing_at(locations[npc.home])
        )
        for npc in npcs
    ]
    entities.append(
        Entity(
            id=PLAYER_ID,
            kind=EntityKind.PLAYER,
            name="Player",
            position=standing_at(locations["square"]),
        )
    )
    return SnapshotMessage(
        time=max(line.timestamp for c in conversations for line in c.lines),
        map_id=MAP_ID,
        entities=entities,
        conversations=[c for c in conversations if c.ended is None],
    )
