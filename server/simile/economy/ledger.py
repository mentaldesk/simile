from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum

from pydantic import Field

from simile.schema import PLAYER_ID, Id, Model, Timestamp

OUTSIDE = "outside"
"""The world beyond the village: it pays wages and pensions, and takes rent and supplies."""
PLAYER = PLAYER_ID
"""The player, who isn't a resident: their money is in the ledger but not in what residents hold."""
_NOT_RESIDENTS = frozenset({OUTSIDE, PLAYER})


class Kind(StrEnum):
    WAGE = "wage"
    PENSION = "pension"
    RENT = "rent"
    GROCERIES = "groceries"
    SUPPLIES = "supplies"
    PURCHASE = "purchase"
    """Paying at a shop, to whoever runs it, or outside the village if nobody does."""
    LOAN = "loan"
    """One resident lending another money."""
    REPAYMENT = "repayment"
    """Paying a loan back."""
    SALVAGE = "salvage"
    """The player selling salvage to a buyer in the tunnels."""
    FOUND = "found"
    """Money the player picks up, such as a secret's cash."""


class Entry(Model):
    at: Timestamp
    kind: Kind
    amount: float = Field(gt=0, allow_inf_nan=False)
    payer: Id
    payee: Id
    place: Id | None = Field(
        default=None,
        description="The shop, for purchases and supplies; the buyer, for salvage; and the "
        "pickup, for money found.",
    )


class Ledger:
    """Every movement of money since the opening balances: the residents', whose balances it
    opens on, and the player's."""

    def __init__(self, opening: Mapping[Id, float], entries: Iterable[Entry] = ()) -> None:
        self.opening = dict(opening)
        self.entries: list[Entry] = list(entries)

    def record(self, entry: Entry) -> None:
        self.entries.append(entry)

    def came_in(self) -> float:
        """Money into residents' hands from outside the village or from the player."""
        return sum(
            entry.amount
            for entry in self.entries
            if entry.payer in _NOT_RESIDENTS and entry.payee not in _NOT_RESIDENTS
        )

    def went_out(self) -> float:
        """Money out of residents' hands to outside the village or to the player."""
        return sum(
            entry.amount
            for entry in self.entries
            if entry.payer not in _NOT_RESIDENTS and entry.payee in _NOT_RESIDENTS
        )

    def net(self, party: Id) -> float:
        """What `party` has been paid since the opening balances, less what they've paid."""
        return sum(
            entry.amount if entry.payee == party else -entry.amount
            for entry in self.entries
            if party in (entry.payer, entry.payee)
        )

    def by_kind(self) -> Counter[Kind]:
        totals: Counter[Kind] = Counter()
        for entry in self.entries:
            totals[entry.kind] += entry.amount
        return totals

    def held(self) -> dict[Id, float]:
        """What each resident holds by the ledger: their opening balance plus everything since."""
        held = dict(self.opening)
        for entry in self.entries:
            if entry.payer not in _NOT_RESIDENTS:
                held[entry.payer] = held.get(entry.payer, 0.0) - entry.amount
            if entry.payee not in _NOT_RESIDENTS:
                held[entry.payee] = held.get(entry.payee, 0.0) + entry.amount
        return held

    def gap(self, holdings: Mapping[Id, float]) -> float:
        """The change in what residents hold, less money in and plus money out: 0 when every
        movement went through the ledger."""
        change = sum(holdings.values()) - sum(self.opening.values())
        return change - (self.came_in() - self.went_out())
