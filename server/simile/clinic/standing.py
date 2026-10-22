from simile.clinic.config import DEFAULT_CONFIG, ClinicConfig
from simile.protocol import Entity, EntityKind, Position, SnapshotMessage
from simile.schema import Conversation, Npc, Pose
from simile.world.map import Spot
from simile.world.movement import Movement


def spot_of(movement: Movement, config: ClinicConfig = DEFAULT_CONFIG) -> Spot:
    return next(s for town in movement.maps.values() for s in town.spots if s.id == config.spot)


def standing(
    snapshot: SnapshotMessage,
    doctor: Npc,
    movement: Movement,
    live: list[Conversation],
    config: ClinicConfig = DEFAULT_CONFIG,
) -> SnapshotMessage:
    """The snapshot with the doctor at their spot in the clinic, and any talk with them."""
    spot = spot_of(movement, config)
    entity = Entity(
        id=doctor.id,
        kind=EntityKind.NPC,
        name=doctor.name,
        position=Position(x=spot.x, y=spot.y, map=spot.map),
        pose=Pose.STANDING,
        facing=spot.facing,
    )
    entities = [*snapshot.entities, entity]
    return snapshot.model_copy(
        update={"entities": entities, "conversations": [*snapshot.conversations, *live]}
    )
