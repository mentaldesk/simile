import json
import logging
from collections.abc import Callable, Collection
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from starlette.applications import Starlette

from simile.player.config import DEFAULT_CONFIG as PLAYER_CONFIG
from simile.player.lamp import DEFAULT_LAMP
from simile.player.where import here, location
from simile.schema import PRESENT, Body, BodyPart, Effect, EffectKind, Id, Location, Player
from simile.sim import Clock
from simile.world.map import FLOORS, MAP_DIR
from simile.world.movement import Movement, inside, spot_of
from simile.world.paths import Spot

logger = logging.getLogger(__name__)

HOUR = 3600.0
KIDNEYS: tuple[BodyPart, ...] = ("left_kidney", "right_kidney")
BED = "bed"
FURNITURE_LAYER = "furniture"


class HealthConfig(BaseModel):
    """How the player heals, what a rat bite does, and how their ailments fade."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    home: Id = Field(default=PLAYER_CONFIG.home, description="Where they heal fastest.")
    heal: float = Field(
        default=0.1,
        ge=0,
        description="How much health comes back each sim hour while someone's playing: from none "
        "to full in ten hours.",
    )
    heal_at_home: float = Field(
        default=0.5, ge=0, description="How much comes back each sim hour at home: two hours."
    )
    rest: float = Field(
        default=DEFAULT_LAMP.charge,
        gt=0,
        description="Real seconds resting in their bed at home, once they've lain down, takes to "
        "heal them from none to full, whatever the sim's speed: as long as a plug takes to charge "
        "the lamp. They rest from `rest` until they're full, move off the bed, are infected, "
        "collapse or get up.",
    )
    lie_down: float = Field(
        default=0.8,
        ge=0,
        description="Real seconds lying down in bed takes, before resting heals them faster.",
    )
    waking: float = Field(
        default=0.25, gt=0, le=1, description="Their health when they wake after collapsing."
    )
    bitten: float = Field(
        default=0.2,
        gt=0,
        le=1,
        description="How much stronger each bite makes the `rat_bite` effect, up to 1.",
    )
    infects: float = Field(
        default=2.0,
        gt=0,
        description="Sim hours after a bite that it turns into an infection if it's still there: "
        "a single bite fades first, a handful don't.",
    )
    infection: float = Field(
        default=0.02,
        ge=0,
        description="The health an infection takes each sim hour at full strength. While "
        "infected, none comes back.",
    )
    fades: dict[EffectKind, float | None] = Field(
        default={EffectKind.RAT_BITE: 0.25, EffectKind.INFECTION: None, EffectKind.RADIATION: 0.05},
        description="The strength each kind of effect loses each sim hour with both kidneys, or "
        "None for one that lasts until it's treated.",
    )
    one_kidney: float = Field(
        default=0.5,
        gt=0,
        le=1,
        description="Of their usual pace, how fast an effect fades with one kidney.",
    )


DEFAULT_HEALTH = HealthConfig()


def health_of(app: Starlette) -> "Health":
    """The player's health, on `app.state.health` from the player's `running` hook, for creatures
    to hurt and bite them. Look it up when they do, not at startup."""
    return app.state.health


def beds_in(home: Location, directory: Path = MAP_DIR) -> frozenset[Spot]:
    """Every cell a bed covers on `home`'s floors, read from their maps' furniture."""
    cells: set[Spot] = set()
    for map_id in (home.map, *(floor.map for floor in home.floors)):
        paths = (directory / FLOORS / f"{map_id}.tmj", directory / f"{map_id}.tmj")
        path = next((path for path in paths if path.exists()), None)
        if path is None:
            continue
        data = json.loads(path.read_text())
        size = data["tilewidth"]
        furniture = (layer for layer in data["layers"] if layer["name"] == FURNITURE_LAYER)
        pieces = (piece for layer in furniture for piece in layer["objects"])
        for bed in (piece for piece in pieces if piece["name"] == BED):
            x, y = round(bed["x"] / size), round(bed["y"] / size)
            across, down = range(round(bed["width"] / size)), range(round(bed["height"] / size))
            cells.update(Spot(map_id, x + dx, y + dy) for dx in across for dy in down)
    return frozenset(cells)


def kidneys(body: Body) -> int:
    return sum(getattr(body, kidney) == PRESENT for kidney in KIDNEYS)


class Health:
    """The player's health and ailments: hurting, healing, fading, an untreated bite turning
    infected, resting in bed, and collapsing at none. Tick it on the sim loop. `beds` are the cells
    where they can rest, by default the beds in their home."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        clock: Clock,
        *,
        playing: Callable[[], bool] = lambda: True,
        collapse: Callable[[], None] = lambda: None,
        beds: Collection[Spot] | None = None,
        config: HealthConfig = DEFAULT_HEALTH,
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.playing = playing
        self.collapse = collapse
        self.config = config
        if beds is None:
            home = location(movement, config.home)
            beds = frozenset() if home is None else beds_in(home)
        self.beds = frozenset(beds)
        self.lain: Spot | None = None
        self.lying = 0.0

    def tick(self, dt: float) -> None:
        if not self.playing():
            return
        hours = dt / HOUR
        self._fade(hours)
        self._infect()
        infection = self.effect(EffectKind.INFECTION)
        if infection is not None:
            self.lain = None
            self.hurt(self.config.infection * infection.strength * hours)
        elif self.player.health < 1:
            self.player.health = min(self.player.health + self.healing(dt), 1.0)
        if self.resting():
            self.lying -= dt / self.clock.speed
            if self.player.health >= 1:
                self.lain = None

    def rest(self, on: bool, *, woken: bool = False) -> bool:
        """Lies them down in the bed where they stand, or gets them up. Whether it did. Having
        `woken` there from a collapse, they're lying down already."""
        if not on:
            resting = self.resting()
            self.lain = None
            return resting
        bed = self.bed()
        infected = self.effect(EffectKind.INFECTION) is not None
        if bed is None or self.resting() or self.player.health >= 1 or infected:
            return False
        self.lain, self.lying = bed, 0.0 if woken else self.config.lie_down
        return True

    def home_bed(self) -> Spot | None:
        """The bed they wake in after collapsing: one of their `beds`."""
        return min(self.beds, default=None)

    def hurt(self, damage: float) -> None:
        """Takes `damage` of their health, collapsing them at none."""
        health = self.player.health - damage
        if health > 0:
            self.player.health = health
            return
        self.player.health = self.config.waking
        self.lain = None
        logger.info("%s  The player has no health left", self.clock)
        self.collapse()

    def bite(self, damage: float) -> None:
        """A rat bites them: it takes `damage`, and the bite may turn infected if it isn't
        treated."""
        self.afflict(EffectKind.RAT_BITE, self.config.bitten)
        self.hurt(damage)

    def afflict(self, kind: EffectKind, strength: float) -> None:
        """Gives them `kind` at `strength`, or makes the one they have that much stronger, up to
        1, keeping when they first got it."""
        had = self.effect(kind)
        if had is None:
            fades, now = self.fading(kind), self.clock.now
            effect = Effect(kind=kind, strength=min(strength, 1.0), fades=fades, since=now)
            self.player.effects = [*self.player.effects, effect]
            return
        stronger = had.model_copy(update={"strength": min(had.strength + strength, 1.0)})
        self.player.effects = [stronger if e is had else e for e in self.player.effects]

    def effect(self, kind: EffectKind) -> Effect | None:
        return next((effect for effect in self.player.effects if effect.kind is kind), None)

    def fading(self, kind: EffectKind) -> float | None:
        """How fast `kind` fades now, slower with one kidney, or None if it lasts until treated."""
        fades = self.config.fades.get(kind)
        if fades is None:
            return None
        return fades if kidneys(self.player.body) == 2 else fades * self.config.one_kidney

    def healing(self, dt: float) -> float:
        """How much health comes back in `dt` sim seconds where they stand, if nothing stops it."""
        if self.resting() and self.lying < 1e-9:
            return dt / self.clock.speed / self.config.rest
        rate = self.config.heal_at_home if self.at_home() else self.config.heal
        return rate * dt / HOUR

    def bed(self) -> Spot | None:
        """The cell of one of their `beds` where they stand."""
        at = here(self.movement)
        spot = None if at is None else spot_of(at)
        return spot if spot in self.beds else None

    def resting(self) -> bool:
        """Whether they're lying in bed, from `rest` until they're full, move off it, are infected,
        collapse or get up."""
        if self.lain is not None and self.bed() != self.lain:
            self.lain = None
        return self.lain is not None

    def at_home(self) -> bool:
        at, home = here(self.movement), location(self.movement, self.config.home)
        return at is not None and home is not None and inside(home, at)

    def _fade(self, hours: float) -> None:
        if not self.player.effects:
            return
        kept = []
        for effect in self.player.effects:
            fades = self.fading(effect.kind) if effect.kind in self.config.fades else effect.fades
            strength = effect.strength - (fades or 0.0) * hours
            if strength > 1e-9:
                kept.append(effect.model_copy(update={"strength": strength, "fades": fades}))
        self.player.effects = kept

    def _infect(self) -> None:
        bite = self.effect(EffectKind.RAT_BITE)
        if bite is None or self.clock.now - bite.since < timedelta(hours=self.config.infects):
            return
        self.player.effects = [e for e in self.player.effects if e is not bite]
        self.afflict(EffectKind.INFECTION, bite.strength)
        logger.info("%s  The player's rat bite turns infected", self.clock)
