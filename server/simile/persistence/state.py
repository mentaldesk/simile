import math

from simile.behaviour import Activity, Behaviour, Goal, GoalChosen, Need
from simile.schema import Id, Model, Tile, Timestamp
from simile.world import Point


class SavedNpc(Model):
    position: Tile
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
    return Tile(x=math.floor(point.x + 0.5), y=math.floor(point.y + 0.5))


def capture(behaviour: Behaviour) -> SavedWorld:
    now, movement = behaviour.clock.now, behaviour.movement
    return SavedWorld(
        now=now,
        npcs={
            npc: SavedNpc(
                position=tile_of(movement.position(npc)),
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
    who was walking or talking decides again on the next think. NPCs who weren't saved start
    afresh."""
    clock, movement = behaviour.clock, behaviour.movement
    saved = {npc: world.npcs[npc] for npc in behaviour.minds if npc in world.npcs}
    for npc in behaviour.minds:
        movement.stop(npc)
    clock.now = world.now
    for _ in range(2):  # the second pass gets tiles that someone was still standing on
        for npc, state in saved.items():
            if movement.position(npc) != (state.position.x, state.position.y):
                movement.place(npc, state.position)
    behaviour.start()  # again, so needs rise from the restored time rather than the first start
    for npc, state in saved.items():
        mind = behaviour.minds[npc]
        if mind.walk is not None:
            movement.stop(npc)
            mind.walk = None
        mind.goal = Goal(state.activity, state.target)
        mind.needs.update(state.needs)
        mind.since, mind.until = state.since, state.until or clock.now
        mind.cooldowns = dict(state.cooldowns)
        behaviour.bus.publish(GoalChosen(npc, state.activity.value, state.target))
