from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum

from pydantic import Field

from simile.schema import Id, Model, Timestamp

OUTSIDE = "outside"
"""The world beyond the village: it pays wages and pensions, and takes rent and supplies."""


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


class Entry(Model):
    at: Timestamp
    kind: Kind
    amount: float = Field(gt=0, allow_inf_nan=False)
    payer: Id
    payee: Id
    place: Id | None = Field(default=None, description="The shop, for purchases and supplies.")


class Ledger:
    """Every movement of money since the opening balances."""

    def __init__(self, opening: Mapping[Id, float], entries: Iterable[Entry] = ()) -> None:
        self.opening = dict(opening)
        self.entries: list[Entry] = list(entries)

    def record(self, entry: Entry) -> None:
        self.entries.append(entry)

    def came_in(self) -> float:
        return sum(entry.amount for entry in self.entries if entry.payer == OUTSIDE)

    def went_out(self) -> float:
        return sum(entry.amount for entry in self.entries if entry.payee == OUTSIDE)

    def by_kind(self) -> Counter[Kind]:
        totals: Counter[Kind] = Counter()
        for entry in self.entries:
            totals[entry.kind] += entry.amount
        return totals

    def held(self) -> dict[Id, float]:
        """What each resident holds by the ledger: their opening balance plus everything since."""
        held = dict(self.opening)
        for entry in self.entries:
            if entry.payer != OUTSIDE:
                held[entry.payer] = held.get(entry.payer, 0.0) - entry.amount
            if entry.payee != OUTSIDE:
                held[entry.payee] = held.get(entry.payee, 0.0) + entry.amount
        return held

    def gap(self, holdings: Mapping[Id, float]) -> float:
        """The change in what residents hold, less money in and plus money out: 0 when every
        movement went through the ledger."""
        change = sum(holdings.values()) - sum(self.opening.values())
        return change - (self.came_in() - self.went_out())
