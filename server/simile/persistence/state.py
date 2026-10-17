from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.schema import VILLAGE_MAP, Id, Key, MapTile, Model, Tile, Timestamp
from simile.world.movement import Point, cell_of


class SavedNpc(Model):
    position: Tile
    map: Key = VILLAGE_MAP
    activity: Activity
    target: str | None = None
    needs: dict[Need, float]
    since: Timestamp
    until: Timestamp | None = None
    cooldowns: dict[Id, Timestamp] = {}


class SavedWorld(Model):
    """What R2's database doesn't already keep: the time, and where each NPC is and what
    they're up to."""

    now: Timestamp
    npcs: dict[Id, SavedNpc]


def tile_of(point: Point) -> Tile:
    x, y = cell_of(point)
    return Tile(x=x, y=y)


def capture(behaviour: Behaviour) -> SavedWorld:
    now, movement = behaviour.clock.now, behaviour.movement
    return SavedWorld(
        now=now,
        npcs={
            npc: SavedNpc(
                position=tile_of(movement.position(npc)),
                map=movement.position(npc).map,
                activity=mind.goal.activity,
                target=mind.goal.target,
                needs=dict(mind.needs),
                since=mind.since,
                until=mind.until,
                cooldowns={other: end for other, end in mind.cooldowns.items() if end > now},
            )
            for npc, mind in behaviour.minds.items()
        },
    )


def restore(world: SavedWorld, behaviour: Behaviour) -> None:
    """Set the clock and put each NPC back where they were, doing what they were doing. Anyone
    who was walking or talking decides again on the next think. NPCs who weren't saved carry
    on from their first start."""
    movement = behaviour.movement
    saved = {npc: world.npcs[npc] for npc in behaviour.minds if npc in world.npcs}
    for npc in saved:
        movement.stop(npc)
    behaviour.clock.now = world.now
    for _ in range(2):  # the second pass gets tiles that someone was still standing on
        for npc, state in saved.items():
            x, y = state.position.x, state.position.y
            if movement.position(npc) != Point(x, y, state.map):
                movement.place(npc, MapTile(map=state.map, x=x, y=y))
    for npc, state in saved.items():
        behaviour.restore(
            npc,
            Goal(state.activity, state.target),
            state.needs,
            state.since,
            state.until,
            state.cooldowns,
        )
