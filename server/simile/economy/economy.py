import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from starlette.applications import Starlette

from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.cafe.config import DEFAULT_CONFIG as CAFE
from simile.cafe.events import Served
from simile.economy.config import DEFAULT_CONFIG, EconomyConfig, Shop
from simile.economy.ledger import OUTSIDE, Entry, Kind, Ledger
from simile.schema import Id, Npc, PayKind
from simile.sim import Clock

logger = logging.getLogger(__name__)

HOUR = timedelta(hours=1)


@dataclass
class Turn:
    """One shift on one day, as it went."""

    npc: Id
    start: datetime
    end: datetime
    arrived: datetime | None = None
    """When they were first at work during it."""
    worked: float = 0.0
    """Hours at work during it."""
    overtime: float = 0.0
    """Hours at work straight after it."""

    def late(self, grace: timedelta) -> bool:
        return self.arrived is not None and self.arrived - self.start > grace


class Economy:
    """Every resident's money, and the ledger every movement of it goes through: wages,
    pensions, rent, groceries, and paying at the shops. Tick it on the sim loop."""

    def __init__(
        self, clock: Clock, behaviour: Behaviour, *, config: EconomyConfig = DEFAULT_CONFIG
    ) -> None:
        self.clock = clock
        self.behaviour = behaviour
        self.config = config
        npcs = behaviour.npcs.values()
        self.money: dict[Id, float] = {npc.id: npc.money for npc in npcs}
        self.ledger = Ledger(self.money)
        self.keepers: dict[Id, Id] = {
            npc.workplace: npc.id
            for npc in npcs
            if npc.pay and npc.pay.kind is PayKind.TAKINGS and npc.workplace in config.shops
        }
        """Who runs each shop, taking what it takes."""
        self.settled = clock.now.date()
        """The last day rent and pensions were settled for, at its start."""
        self.turns: list[Turn] = []
        """Every shift that started while the economy was watching."""
        self.since = clock.now
        self._turns: dict[Id, Turn] = {}
        self._owed: dict[Id, float] = {}
        self._meals: dict[Id, datetime] = {}
        self._served: dict[Id, datetime] = {}
        self._elapsed = 0.0
        self._checked = clock.now

    def restore(self, money: Mapping[Id, float], settled: date) -> None:
        """Put back saved balances, for residents who are still here, and open the ledger on
        them. Anyone the save leaves out has what they started with."""
        npcs = self.behaviour.npcs.values()
        self.money = {npc.id: money.get(npc.id, npc.money) for npc in npcs}
        self.ledger = Ledger(self.money)
        self.settled = settled
        self.since = self._checked = self.clock.now

    def money_of(self, npc: Npc) -> float | None:
        """B1's money hook."""
        return self.money.get(npc.id)

    def price(self, npc: Npc, goal: Goal) -> float:
        """B1's price hook: groceries for a meal at home, and at a shop that's serving a drink,
        unless the café served them one lately and they'd just sit down, and a meal if they'd
        eat."""
        mind = self.behaviour.minds[npc.id]
        appetite = self.behaviour.config.urgency[Need.HUNGER].appetite
        hungry = mind.needs[Need.HUNGER] >= appetite
        if goal == Goal(Activity.HOME, npc.home):
            return self.config.groceries if hungry else 0.0
        shop = self._shop(goal)
        if shop is None or self.behaviour.hooks.supply(goal, Need.HUNGER) <= 0:
            return 0.0
        last = self._served.get(npc.id)
        ordering = last is None or self.clock.now - last >= timedelta(minutes=CAFE.again)
        return (shop.drink if ordering else 0.0) + (shop.meal if hungry else 0.0)

    def earnings(self, npc: Npc, goal: Goal) -> float:
        """B1's earnings hook: what an hour at work pays them."""
        if npc.pay is None or goal != Goal(Activity.WORK, npc.workplace):
            return 0.0
        if npc.pay.kind is PayKind.TAKINGS:
            return self.config.takings
        if npc.pay.kind is PayKind.WAGE and npc.pay.amount is not None:
            return npc.pay.amount
        return 0.0

    def on_served(self, event: Served) -> None:
        """The café served a resident: they pay for the drink."""
        shop = self.config.shops.get("coffee_shop")
        if event.customer in self.money:
            self._served[event.customer] = self.clock.now
        if event.customer in self.money and shop is not None and shop.drink:
            self.buy(event.customer, "coffee_shop", shop.drink)

    def buy(self, customer: Id, place: Id, amount: float) -> None:
        """Pay at a shop. Whoever runs it takes the money and buys in the supplies."""
        keeper = self.keepers.get(place, OUTSIDE)
        if keeper != customer:
            self.pay(customer, keeper, amount, Kind.PURCHASE, place)
        if keeper != OUTSIDE:
            self.pay(
                keeper, OUTSIDE, amount * self.config.shops[place].supplies, Kind.SUPPLIES, place
            )

    def pay(self, payer: Id, payee: Id, amount: float, kind: Kind, place: Id | None = None) -> None:
        """Move money through the ledger. Residents can go below nothing, as for rent they can't
        cover."""
        if amount <= 0:
            return
        entry = Entry(
            at=self.clock.now, kind=kind, amount=amount, payer=payer, payee=payee, place=place
        )
        if payer != OUTSIDE:
            self.money[payer] -= amount
        if payee != OUTSIDE:
            self.money[payee] += amount
        self.ledger.record(entry)

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed < self.config.every - 1e-9:
            return
        self._elapsed = 0.0
        now = self.clock.now
        hours, self._checked = (now - self._checked) / HOUR, now
        self._settle(now)
        for npc in self.behaviour.npcs.values():
            working = self.behaviour.working(npc.id)
            self._attend(npc, working, hours, now)
            self._wages(npc, working, hours)
            self._meal(npc)

    def _settle(self, now: datetime) -> None:
        """Rent and a day's pension for each day that's started since the last."""
        while self.settled < now.date():
            self.settled += timedelta(days=1)
            for npc in self.behaviour.npcs.values():
                self.pay(npc.id, OUTSIDE, self.config.rent, Kind.RENT)
                if npc.pay and npc.pay.kind is PayKind.PENSION and npc.pay.amount:
                    self.pay(OUTSIDE, npc.id, npc.pay.amount / 7, Kind.PENSION)

    def _attend(self, npc: Npc, working: bool, hours: float, now: datetime) -> None:
        turn = self._turns.get(npc.id)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        shift = next((shift for shift in npc.shifts if shift.covers(now)), None)
        if shift is not None:
            start = midnight + shift.start * HOUR
            if turn is None or turn.start != start:
                turn = Turn(npc.id, start, midnight + shift.end * HOUR)
                self._turns[npc.id] = turn
                if start >= self.since:
                    self.turns.append(turn)
        elif turn is not None and now >= turn.end and not working:
            del self._turns[npc.id]
            turn = None
        if turn is None or not working:
            return
        if now < turn.end:
            turn.worked += hours
            turn.arrived = turn.arrived or now
        else:
            turn.overtime += hours

    def _wages(self, npc: Npc, working: bool, hours: float) -> None:
        if npc.pay is None or npc.pay.kind is not PayKind.WAGE or npc.pay.amount is None:
            return
        owed = self._owed.get(npc.id, 0.0) + (hours if working else 0.0)
        if owed and (not working or owed >= self.config.pay_every):
            self.pay(OUTSIDE, npc.id, owed * npc.pay.amount, Kind.WAGE)
            owed = 0.0
        self._owed[npc.id] = owed

    def _meal(self, npc: Npc) -> None:
        """Charge for a meal once they start eating it: groceries at home, or at a shop."""
        mind = self.behaviour.minds[npc.id]
        if mind.eating.get(Need.HUNGER) != mind.since or self._meals.get(npc.id) == mind.since:
            return
        self._meals[npc.id] = mind.since
        if mind.goal == Goal(Activity.HOME, npc.home):
            self.pay(npc.id, OUTSIDE, self.config.groceries, Kind.GROCERIES)
        elif (shop := self._shop(mind.goal)) is not None and mind.goal.target is not None:
            self.buy(npc.id, mind.goal.target, shop.meal)

    def _shop(self, goal: Goal) -> Shop | None:
        if goal.target is None or goal.activity.value != goal.target:
            return None
        return self.config.shops.get(goal.target)


def economy_of(app: Starlette) -> Economy:
    """The server's `Economy` on `app.state.economy`, created on first use."""
    if not hasattr(app.state, "economy"):
        from simile.behaviour import behaviour_of
        from simile.sim import world_of

        app.state.economy = Economy(world_of(app).clock, behaviour_of(app))
    return app.state.economy
