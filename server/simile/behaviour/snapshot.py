from simile.behaviour.mind import Behaviour
from simile.protocol import Entity, EntityKind, Position, SnapshotMessage
from simile.schema import PLAYER_ID
from simile.world import Point

PLAYER_NAME = "Player"
PLAYER_SPAWN = "square"


def snapshot(behaviour: Behaviour) -> SnapshotMessage:
    """The player is in the square until their first `player_move`, and the snapshot's map is
    the one they're on."""
    movement = behaviour.movement
    positions = movement.entities()
    entities = [
        Entity(id=npc.id, kind=EntityKind.NPC, name=npc.name, position=_position(point))
        for npc in behaviour.npcs.values()
        if (point := positions.get(npc.id)) is not None
    ]
    for entity in entities:
        entity.pose, entity.facing = movement.posture(entity.id)
    if PLAYER_ID in positions:
        player = _position(positions[PLAYER_ID])
    else:
        square = movement.town.location(PLAYER_SPAWN)
        player = Position(x=square.entry.x, y=square.entry.y, map=square.map)
    entities.append(Entity(id=PLAYER_ID, kind=EntityKind.PLAYER, name=PLAYER_NAME, position=player))
    return SnapshotMessage(
        time=behaviour.clock.now,
        map_id=player.map,
        entities=entities,
        conversations=behaviour.hooks.conversations(),
    )


def _position(point: Point) -> Position:
    return Position(x=point.x, y=point.y, map=point.map)
