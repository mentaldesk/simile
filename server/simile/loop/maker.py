"""Stage 3's loop, after stage 2's: README.md."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from simile.economy import Kind
from simile.loop.player import LOCKERS, SCRAP, LoopPlayer, Refused
from simile.loop.playthrough import LANDING, OUTSIDE_THE_CLINIC, Playthrough
from simile.machines.materials import plastic
from simile.machines.printer import PISTOL, ROUNDS
from simile.protocol import LampMessage
from simile.schema import (
    POWER_CELLS,
    Bionic,
    Corpse,
    CreatureKind,
    Id,
    ItemKind,
    Player,
    SideFacing,
)
from simile.street.jump import JUMP
from simile.street.sewers import DEN_BEDROLL, DEN_LADDER, DEN_SECRET, PRINTER_CRATES, SEWERS
from simile.world.paths import Spot

PRINTER, RECYCLER = "printer_3d", "recycler"
SPOOL = "maker_space_spool"
SHEET = "metro_track_rubble"
"""The metal sheet, on the metro's disused track."""
BOT = "metro_bot_1"
"""The bot under the catwalk, whose haul holds scrap."""
PLASTIC = plastic(1).id
RATS = 2
SCRAP_PICKUPS = ("sewers_salvage_5",)
"""A lead pipe past the gate, pressed for the rounds the bot takes."""
DYING = 120.0
"""Sim seconds they give the bats."""
WHOLE = 30.0
"""Sim seconds they rest in bed at most after waking."""


@dataclass
class Made:
    """Stage 3's loop as it ended."""

    end: datetime
    away: timedelta
    player: Player
    shot: Counter[CreatureKind]
    hurt: list[str]
    """Each time they lost health but to the bats they let kill them."""
    died: list[str]
    corpse: Corpse
    """Their body as it lay when they woke."""
    haul: list[str]
    salvaged: list[str]
    refitted: list[Bionic]
    earned: dict[Kind, float]


class MakerSpace:
    """The printer, the pistol, the recycler, a death on purpose and the body salvaged."""

    def __init__(self, play: Playthrough) -> None:
        self.play = play
        self.player: LoopPlayer = play.player
        self.saves = play.saves
        self.salvaged: list[str] = []
        self.refitted: list[Bionic] = []

    async def run(self) -> Made:
        p = self.player
        hurt = len(p.hurt)
        await self.the_printer()
        await self.the_pistol()
        await self.rats_shot()
        await self.a_dog()
        await self.the_recycler()
        haul = await self.the_bot()
        dying = len(p.hurt)
        corpse = await self.die_on_purpose()
        woke = len(p.hurt)
        await self.salvaged_and_refitted(corpse)
        await self.rounds_from_scrap()
        return Made(
            p.world.clock.now,
            p.away,
            p.player.model_copy(deep=True),
            p.shot,
            p.hurt[hurt:dying] + p.hurt[woke:],
            p.died,
            corpse,
            haul,
            self.salvaged,
            self.refitted,
            self.play.earned(),
        )

    def carried(self, id: Id) -> float:
        return sum(item.amount for item in self.player.player.items if item.id == id)

    async def the_printer(self) -> None:
        """The metal sheet and the actuator, with the two wires kept back from the datajack's."""
        p = self.player
        await p.search(SHEET)
        await p.search(PRINTER_CRATES)
        missing = {id: n - self.carried(id) for id, n in p.machines[PRINTER].parts.items()}
        if any(short > 0 for short in missing.values()):
            raise Refused(f"Short of the printer's parts: {missing}")
        await p.to(p.stand_at(PRINTER))
        await self.saves.write("printer", p, spool=p.stand_at(SPOOL).x)
        await p.repair(PRINTER)

    async def the_pistol(self) -> None:
        """Aris's spool, printed into a pistol and a magazine of rounds, loaded, and the ration
        pack in the lockers, so rats keep to their nests to be shot."""
        p = self.player
        await p.search(SPOOL)
        await p.make(PRINTER, PISTOL.id)
        await p.make(PRINTER, ROUNDS.id)
        await p.reload()
        await p.store(*(item.id for item in p.player.items if item.kind is ItemKind.FOOD))

    async def rats_shot(self) -> None:
        """From the biggest nest's floor, each rat that comes for the ration pack."""
        p = self.player
        stand, _ = self.play.nest()
        await p.to(stand)
        await p.shoot(CreatureKind.RAT, RATS)

    async def a_dog(self) -> None:
        """From the den's floor short of its ladder, out of the dogs' reach, then up it for the
        delver's batteries, and a lead pipe on the way back."""
        p = self.player
        den = self.play.pickup(DEN_SECRET).x
        stand = Spot(SEWERS, den + DEN_LADDER - 2, LANDING.y)
        await p.to(stand)
        await self.saves.write("dog", p, facing=SideFacing.EAST)
        await p.shoot(CreatureKind.DOG, 1)
        await p.search(DEN_BEDROLL)
        for id in SCRAP_PICKUPS:
            await p.take(self.play.pickup(id))

    async def the_recycler(self) -> None:
        """The Apex board kept from the hall's ledge and the den's batteries repair it, and the
        lead pipe presses into plastic for another magazine."""
        p = self.player
        await p.repair(RECYCLER)
        await p.make(RECYCLER, PLASTIC)
        await p.make(PRINTER, ROUNDS.id)
        await p.reload()

    async def the_bot(self) -> list[str]:
        """Shoots the bot from out of its sight along its floor, and takes its haul."""
        p = self.player
        bot = p.creatures[BOT]
        row = round(bot.position.y)
        town = p.movement.maps[bot.position.map]
        x = next(
            x
            for x in range(round(bot.position.x) + 10, round(bot.position.x) + 7, -1)
            if town.standing(x, row)
        )
        await p.to(Spot(bot.position.map, x, row))
        await self.saves.write("bot", p, facing=SideFacing.WEST, bot=BOT)
        left = list(p.player.left)
        await p.shoot(CreatureKind.BOT, 1)
        await p.wait(0.5)
        piles = [pile for pile in p.player.left if pile not in left]
        if not piles:
            raise Refused(f"{BOT} dropped no haul")
        return await p.haul(piles[0].at)

    async def die_on_purpose(self) -> Corpse:
        """Stores the pistol, then lets the bats in a room their own legs reach kill them by
        lamplight, and wakes whole in bed."""
        p = self.player
        await p.to(p.stand_at(LOCKERS))
        await self.saves.write("stash", p)
        await p.store(*(id for id in (PISTOL.id, ROUNDS.id, PLASTIC) if self.carried(id)))
        stand = self.under_bats()
        await p.to(stand)
        await self.saves.write("death", p)
        deaths = len(p.died)
        p.send(LampMessage(on=True))
        for _ in range(round(DYING / 0.5)):
            await p.wait(0.5)
            if len(p.died) > deaths:
                break
        else:
            raise Refused(f"The bats didn't kill them in {DYING:g} s at {stand}")
        p.note(f"Died by the bats, and woke at {p.where}")
        for _ in range(round(WHOLE / 0.5)):
            if p.player.health >= 0.999:
                break
            await p.wait(0.5)
        p.note(f"Got up at health {p.player.health:.2f}")
        return p.player.corpses[-1]

    def under_bats(self) -> Spot:
        """The floor under a roost of the sewers' first bats that their own legs reach, on no
        bot's floor."""
        p = self.player
        reach = p.reach(JUMP)
        bots = {
            (c.position.map, round(c.position.y))
            for c in p.creatures.values()
            if c.kind is CreatureKind.BOT
        }
        for bat in sorted(p.creatures.values(), key=lambda c: c.id):
            at = bat.position
            if bat.kind is not CreatureKind.BAT or at.map != SEWERS or "cave" in bat.id:
                continue
            town, x = p.movement.maps[at.map], round(at.x)
            row = next(y for y in range(int(at.y) + 1, town.height) if town.standing(x, y))
            if Spot(at.map, x, row) in reach and (at.map, row) not in bots:
                return Spot(at.map, x, row)
        raise Refused("No bats' roost is over a floor their own legs reach")

    async def salvaged_and_refitted(self, corpse: Corpse) -> None:
        """Back to the body on their own legs, then to the clinic with what they took, back for
        the rest until it's gone, and every bionic refitted."""
        p = self.player
        for trip in range(3):
            if p.corpse(corpse.id) is None:
                break
            await p.to(Spot(corpse.at.map, corpse.at.x, corpse.at.y))
            if not trip:
                await self.saves.write("salvage", p, corpse=corpse.id)
            self.salvaged += await p.salvage(corpse.id)
            await self.refit()
        else:
            raise Refused(f"{corpse.id} still holds {p.corpse(corpse.id)}")

    async def refit(self) -> None:
        """Has the doctor refit each bionic they carry, the cell first."""
        p = self.player
        salvaged = [item.bionic for item in p.player.items if item.bionic is not None]
        if not salvaged:
            return
        await p.to(OUTSIDE_THE_CLINIC)
        if not self.refitted:
            await self.saves.write("refit", p)
        await p.clinic()
        for bionic in sorted(salvaged, key=lambda b: b not in POWER_CELLS):
            fittings = p.state.buyer.fittings if p.state.buyer else []
            fitting = next(f for f in fittings if f.bionic is bionic)
            await p.fit(bionic, fitting.parts[0])
            self.refitted.append(bionic)

    async def rounds_from_scrap(self) -> None:
        """Home with the scrap off their body: pressed into plastic, and printed into rounds with
        what's in the lockers."""
        p = self.player
        if not any(item.id in SCRAP for item in p.player.items):
            raise Refused(f"No scrap to haul home: {p.player.items}")
        await p.to(p.stand_at(RECYCLER))
        await self.saves.write("recycle", p)
        await p.make(RECYCLER, PLASTIC)
        await p.take_out(*(item.id for item in p.player.stash.items))
        await p.make(PRINTER, ROUNDS.id)
        await p.reload()
        if not any(item.kind is ItemKind.WEAPON for item in p.player.items):
            raise Refused("They have no pistol at the end")
