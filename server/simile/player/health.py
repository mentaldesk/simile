import logging
from collections.abc import Callable
from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field
from starlette.applications import Starlette

from simile.player.config import DEFAULT_CONFIG as PLAYER_CONFIG
from simile.player.where import here, location
from simile.schema import PRESENT, Body, BodyPart, Effect, EffectKind, Id, Player
from simile.sim import Clock
from simile.world.movement import Movement, inside

logger = logging.getLogger(__name__)

HOUR = 3600.0
KIDNEYS: tuple[BodyPart, ...] = ("left_kidney", "right_kidney")


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


def kidneys(body: Body) -> int:
    return sum(getattr(body, kidney) == PRESENT for kidney in KIDNEYS)


class Health:
    """The player's health and ailments: hurting, healing, fading, an untreated bite turning
    infected, and collapsing at none. Tick it on the sim loop."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        clock: Clock,
        *,
        playing: Callable[[], bool] = lambda: True,
        collapse: Callable[[], None] = lambda: None,
        config: HealthConfig = DEFAULT_HEALTH,
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.playing = playing
        self.collapse = collapse
        self.config = config

    def tick(self, dt: float) -> None:
        if not self.playing():
            return
        hours = dt / HOUR
        self._fade(hours)
        self._infect()
        infection = self.effect(EffectKind.INFECTION)
        if infection is not None:
            self.hurt(self.config.infection * infection.strength * hours)
        elif self.player.health < 1:
            rate = self.config.heal_at_home if self.at_home() else self.config.heal
            self.player.health = min(self.player.health + rate * hours, 1.0)

    def hurt(self, damage: float) -> None:
        """Takes `damage` of their health, collapsing them at none."""
        health = self.player.health - damage
        if health > 0:
            self.player.health = health
            return
        self.player.health = self.config.waking
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
