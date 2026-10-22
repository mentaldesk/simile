from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING

from pydantic import Field, field_validator
from starlette.applications import Starlette

from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.economy import Batch
from simile.persistence.old_cells import moved
from simile.schema import (
    VILLAGE_MAP,
    Id,
    Intention,
    Investigation,
    Key,
    MapTile,
    Model,
    Player,
    Tile,
    Timestamp,
)
from simile.world.movement import Movement, Point, cell_of

if TYPE_CHECKING:
    from simile.economy.economy import Economy


class SavedNpc(Model):
    position: Tile
    map: Key = VILLAGE_MAP
    """The map they're on. A save from before the interiors has none: it's on the iso village."""
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
    player: Player = Field(default_factory=Player)
    """The player. A save from before the player has the starting player."""
    investigation: Investigation = Field(default_factory=Investigation)
    """The incident and the journal. A save from before them has neither."""


def tile_of(point: Point) -> Tile:
    x, y = cell_of(point)
    return Tile(x=x, y=y)


def capture(
    behaviour: Behaviour,
    economy: "Economy | None" = None,
    player: Player | None = None,
    investigation: Investigation | None = None,
) -> SavedWorld:
    """The world as it is now, with copies of `player` and `investigation`, or the starting
    player and an empty investigation without them."""
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
        player=Player() if player is None else player.model_copy(deep=True),
        investigation=Investigation()
        if investigation is None
        else investigation.model_copy(deep=True),
    )


def restore(
    world: SavedWorld,
    behaviour: Behaviour,
    economy: "Economy | None" = None,
    player: Player | None = None,
    investigation: Investigation | None = None,
) -> None:
    """Set the clock and put each NPC back where they were, doing what they were doing, with the
    money they had, what was in their fridges and what they'd said they'd do, and set `player`
    and `investigation` to the saved ones in place, so anyone holding them already has them.
    Anyone saved on one of the iso maps goes to the matching place on the side-view maps
    (`old_cells`). Anyone who was walking or talking decides again on the next think. NPCs who
    weren't saved carry on from their first start, a save from before money opens the ledger on
    everyone's starting money, and one from before fridges stocks them as at the start."""
    movement = behaviour.movement
    saved = {npc: world.npcs[npc] for npc in behaviour.minds if npc in world.npcs}
    for npc in saved:
        movement.stop(npc)
    behaviour.clock.now = world.now
    pending = {
        npc: here
        for npc, state in saved.items()
        if (here := _on_maps(state, movement.maps)) is not None
    }
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
    if player is not None:
        for field in Player.model_fields:
            setattr(player, field, getattr(world.player, field))
    if investigation is not None:
        restored = world.investigation.model_copy(deep=True)
        for field in Investigation.model_fields:
            setattr(investigation, field, getattr(restored, field))


def _on_maps(state: SavedNpc, maps: Mapping[str, object]) -> SavedNpc | None:
    """Where they were, moved from the iso maps if those aren't loaded, or None if they can't
    be put anywhere loaded."""
    if state.map in maps:
        return state
    to = moved(state.map, state.position.x, state.position.y)
    if to is None or to.map not in maps:
        return None
    return state.model_copy(update={"map": to.map, "position": Tile(x=to.x, y=to.y)})


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


def player_of(app: Starlette) -> Player:
    """The player, made on first use. Persistence restores the save into it in place."""
    if not hasattr(app.state, "player"):
        app.state.player = Player()
    return app.state.player


def investigation_of(app: Starlette) -> Investigation:
    """The incident and the journal, empty on first use. Persistence restores the save into it
    in place."""
    if not hasattr(app.state, "investigation"):
        app.state.investigation = Investigation()
    return app.state.investigation
