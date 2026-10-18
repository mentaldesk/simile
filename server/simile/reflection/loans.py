import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from simile.conversation.loans import Ask, Loan, Purse, Repayment
from simile.economy import Kind
from simile.reflection.extraction import Context, Extraction, Relationships
from simile.schema import Flag, Id
from simile.social import loan as debt

if TYPE_CHECKING:
    from simile.economy.economy import Economy


@dataclass(frozen=True)
class Payment:
    """Money a conversation moved between two residents, and the debt flag it opens or
    settles."""

    payer: Id
    payee: Id
    amount: int
    kind: Kind
    opens: Flag | None = None
    settles: Flag | None = None


def payment(
    context: Context,
    extraction: Extraction,
    loan: Loan | None,
    economy: "Economy",
    store: Relationships,
) -> Payment | None:
    """The money the conversation moved, if B3 found the loan the engine set it up to settle
    and the payer holds the money. A loan is capped at what the lender agreed to and can spare."""
    if isinstance(loan, Repayment):
        return _repaid(context, extraction, loan, economy, store)
    if isinstance(loan, Ask) and loan.lends:
        return _lent(context, extraction, loan, economy)
    return None


def _lent(context: Context, extraction: Extraction, ask: Ask, economy: "Economy") -> Payment | None:
    pair = (ask.lender, ask.borrower)
    found = [
        lending
        for lending in extraction.loans
        if (context.who(lending.lender), context.who(lending.borrower)) == pair
    ]
    if not found:
        return None
    held = economy.money.get(ask.lender, 0.0)
    if not 0 < found[0].amount <= held:
        return None
    spare = Purse(held, economy.behaviour.savings(ask.lender)).spare
    amount = math.floor(min(found[0].amount, ask.lends, spare))
    if amount < 1:
        return None
    flag = debt(ask.lender, ask.borrower, amount, context.conversation.id, context.now)
    return Payment(ask.lender, ask.borrower, amount, Kind.LOAN, opens=flag)


def _repaid(
    context: Context,
    extraction: Extraction,
    repayment: Repayment,
    economy: "Economy",
    store: Relationships,
) -> Payment | None:
    flag = repayment.flag
    refs = {ref.strip().upper() for ref in extraction.flags_resolved}
    if not any(context.flags[ref].id == flag.id for ref in refs if ref in context.flags):
        return None
    now = store.relationship(flag.owner, flag.about)
    if now is None or not any(f.id == flag.id and f.resolved is None for f in now.flags):
        return None
    if not 0 < repayment.amount <= economy.money.get(repayment.borrower, 0.0):
        return None
    return Payment(
        repayment.borrower, repayment.lender, repayment.amount, Kind.REPAYMENT, settles=flag
    )
