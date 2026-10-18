import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from itertools import permutations

from simile.behaviour.scoring import finances
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.schema import Flag, Id, Relationship
from simile.social import lent, owed


@dataclass(frozen=True)
class Purse:
    """What someone holds, and their savings target."""

    money: float
    target: float

    def short(self, config: ConversationConfig = DEFAULT_CONFIG, after: float = 0.0) -> bool:
        """Whether they're short enough to borrow, after paying out `after`."""
        return finances(self.money - after, self.target) >= config.borrow_from

    @property
    def spare(self) -> float:
        """What they could lend and still have their savings target."""
        return max(self.money - self.target, 0.0)


@dataclass(frozen=True)
class Ask:
    """One side of a scene asking the other for a loan, as the engine set it up."""

    borrower: Id
    lender: Id
    amount: int
    lends: int
    """What the lender agrees to lend: 0 when they say no."""
    trusted: bool
    """Whether the lender trusts the borrower enough to lend them money."""


@dataclass(frozen=True)
class Repayment:
    """One side of a scene paying back a loan from the other."""

    borrower: Id
    lender: Id
    flag: Flag
    """The loan's debt flag."""

    @property
    def amount(self) -> int:
        return lent(self.flag) or 0


type Loan = Ask | Repayment


def arrange(
    purses: Mapping[Id, Purse],
    feelings: Mapping[Id, Relationship],
    config: ConversationConfig = DEFAULT_CONFIG,
    *,
    declined: Collection[tuple[Id, Id]] = (),
) -> Loan | None:
    """What a scene between the two in `purses` settles about money: a loan paid back by whoever
    can, or else one asked for by whoever is short, of someone they like who hasn't turned them
    down lately (`declined`, as borrower and lender). `feelings[npc]` is how `npc` feels about
    the other. Trust decides whether the lender lends."""
    pairs = list(permutations(purses))
    for borrower, lender in pairs:
        flag = owed(feelings[lender])
        if flag is not None and not purses[borrower].short(config, after=lent(flag) or 0):
            return Repayment(borrower, lender, flag)
    for borrower, lender in pairs:
        purse = purses[borrower]
        if (
            not purse.short(config)
            or feelings[borrower].like < config.ask_like
            or owed(feelings[lender]) is not None
            or (borrower, lender) in declined
        ):
            continue
        amount = min(config.max_loan, tens(purse.target - purse.money, up=True))
        trusted = feelings[lender].trust >= config.lend_trust
        lends = tens(min(amount, purses[lender].spare)) if trusted else 0
        return Ask(borrower, lender, amount, lends, trusted)
    return None


def told(loan: Loan, names: Mapping[Id, str]) -> str:
    """The loan as direction for the scene."""
    borrower, lender = names[loan.borrower], names[loan.lender]
    if isinstance(loan, Repayment):
        return f"{borrower} has the money now, and pays back the {loan.amount} {lender} lent them."
    asks = (
        f"{borrower} is short of money and asks {lender} to lend them {loan.amount} to tide them "
        "over."
    )
    if not loan.trusted:
        return f"{asks} {lender} doesn't trust {borrower} enough to lend money, and says no."
    if not loan.lends:
        return f"{asks} {lender} can't spare it, and says no."
    if loan.lends < loan.amount:
        return f"{asks} {lender} can only spare {loan.lends}, and lends that."
    return f"{asks} {lender} trusts {borrower} and lends it."


def tens(amount: float, *, up: bool = False) -> int:
    rounded = math.ceil(amount / 10) if up else math.floor(amount / 10)
    return max(int(rounded) * 10, 0)
