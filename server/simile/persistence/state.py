from datetime import date
from typing import TYPE_CHECKING

from pydantic import field_validator

from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.economy import Batch
from simile.schema import VILLAGE_MAP, Id, Intention, Key, MapTile, Model, Tile, Timestamp
from simile.world.movement import Movement, Point, cell_of

if TYPE_CHECKING:
    from simile.economy.economy import Economy


class SavedNpc(Model):
    position: Tile
    map: Key = VILLAGE_MAP
    activity: Activity
    target: str | None = None
    needs: dict[Need, float]
    since: Timestamp
    until: Timestamp | None = None
    cooldowns: dict[Id, Timestamp] = {}

    @field_validator("needs", mode="before")
    @classmethod
    def _known(cls, needs: object) -> object:
        """Drops needs B1 no longer has, so a save from before still loads."""
        if isinstance(needs, dict):
            return {need: level for need, level in needs.items() if need in Need}
        return needs


class SavedEconomy(Model):
    money: dict[Id, float]
    settled: date
    """The last day rent and pensions were settled for."""
    fridges: dict[Id, int] | None = None
    """Meals left in each home's fridge. A save from before fridges has none."""
    batches: dict[Id, Batch] | None = None
    """Each shop's latest batch."""


class SavedWorld(Model):
    """What R2's database doesn't already keep: the time, where each NPC is and what they're up
    to, what they've said they'll do, and their money. The ledger's entries are saved as they're
    made, in their own table."""

    now: Timestamp
    npcs: dict[Id, SavedNpc]
    economy: SavedEconomy | None = None
    intentions: list[Intention] = []
    """Everyone's open intentions. A save from before intentions has none."""


def tile_of(point: Point) -> Tile:
    x, y = cell_of(point)
    return Tile(x=x, y=y)


def capture(behaviour: Behaviour, economy: "Economy | None" = None) -> SavedWorld:
    now, movement = behaviour.clock.now, behaviour.movement
    return SavedWorld(
        now=now,
        economy=SavedEconomy(
            money=dict(economy.money),
            settled=economy.settled,
            fridges=dict(economy.fridges),
            batches={shop: batch.model_copy() for shop, batch in economy.batches.items()},
        )
        if economy
        else None,
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
        intentions=behaviour.intentions(),
    )


def restore(world: SavedWorld, behaviour: Behaviour, economy: "Economy | None" = None) -> None:
    """Set the clock and put each NPC back where they were, doing what they were doing, with the
    money they had, what was in their fridges and what they'd said they'd do. Anyone who was
    walking or talking decides again on the next think. NPCs who weren't saved carry on from
    their first start, a save from before money opens the ledger on everyone's starting money,
    and one from before fridges stocks them as at the start."""
    movement = behaviour.movement
    saved = {npc: world.npcs[npc] for npc in behaviour.minds if npc in world.npcs}
    for npc in saved:
        movement.stop(npc)
    behaviour.clock.now = world.now
    pending = dict(saved)
    while free := {npc: state for npc, state in pending.items() if _free(movement, npc, state)}:
        for npc, state in free.items():
            _put(movement, npc, state)
            del pending[npc]
    for _ in range(2):  # the second pass gets tiles that someone was still standing on
        for npc, state in pending.items():
            _put(movement, npc, state)
    for npc, state in saved.items():
        behaviour.restore(
            npc,
            Goal(state.activity, state.target),
            state.needs,
            state.since,
            state.until,
            state.cooldowns,
        )
    behaviour.restore_intentions(world.intentions)
    if economy is not None:
        saved = world.economy
        if saved is None:
            economy.restore({}, world.now.date())
        else:
            economy.restore(saved.money, saved.settled, saved.fridges, saved.batches)


def _free(movement: Movement, npc: Id, state: SavedNpc) -> bool:
    """Whether nobody else is standing on the tile `npc` was saved on."""
    tile = (state.position.x, state.position.y)
    return all(
        other == npc or point.map != state.map or cell_of(point) != tile
        for other, point in movement.entities().items()
    )


def _put(movement: Movement, npc: Id, state: SavedNpc) -> None:
    x, y = state.position.x, state.position.y
    if movement.position(npc) != Point(x, y, state.map):
        movement.place(npc, MapTile(map=state.map, x=x, y=y))
