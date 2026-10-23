import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour.events import GoalChosen
    from simile.persistence import player_of
    from simile.protocol import PlayerMoveMessage, hub_of
    from simile.schema import PLAYER_ID, Bionic, Id
    from simile.sim import world_of
    from simile.street.jump import jump_of
    from simile.street.moves import possible
    from simile.street.sewers import SEWERS
    from simile.world.movement import Point, movement_of
    from simile.world.spots import indifferent, purpose_of

    world, movement = world_of(app), movement_of(app)

    def on_player_move(message: PlayerMoveMessage) -> None:
        position = message.position
        town = movement.maps.get(position.map)
        if town is None:
            logger.warning("Ignored a player_move onto an unknown map: %s", position)
            return
        last = movement.entities().get(PLAYER_ID)
        kept = (last.x, last.y) if last is not None and last.map == position.map else None
        body = player_of(app).body
        entering = last is None or last.map != position.map
        if entering and position.map == SEWERS and Bionic.DATAJACK not in body.bionics:
            logger.warning("Ignored a player_move into the sewers without the datajack")
            return
        jump = jump_of(body)
        if town.kind is not None and not possible(town, position.x, position.y, kept, jump):
            logger.warning("Ignored a player_move to where nobody could be: %s", position)
            return
        movement.track(PLAYER_ID, Point(position.x, position.y, position.map))

    def on_goal(event: GoalChosen) -> None:
        movement.intend(event.npc, purpose_of(event.activity, event.target))

    def affinity(a: Id, b: Id) -> float:
        """B1's affinity, as places score it, once behaviour is running."""
        from simile.behaviour.scoring import affinity as score
        from simile.social import as_of, meet

        behaviour = getattr(app.state, "behaviour", None)
        if behaviour is None or a not in behaviour.npcs:
            return 0.0
        known = behaviour.relationships.relationships(a) if behaviour.relationships else []
        rel = next((r for r in known if r.about == b), None) or meet(behaviour.npcs[a], b)
        now = behaviour.clock.now
        return score(as_of(rel, now, traits=behaviour.traits_of(a)), behaviour.config)

    movement.affinity = affinity
    stops = [
        world.loop.register(movement),
        hub_of(app).subscribe(PlayerMoveMessage, on_player_move),
        world.bus.subscribe(GoalChosen, on_goal),
    ]
    yield
    for stop in reversed(stops):
        stop()
    movement.affinity = indifferent
