import re
from datetime import datetime

from simile.schema import Flag, FlagKind, Id, Relationship

LOAN_ID = re.compile(r"/loan/(\d+)$")


def loan(lender: Id, borrower: Id, amount: int, conversation: str, when: datetime) -> Flag:
    """The debt flag a loan leaves, the lender's about the borrower. Its id carries the amount,
    so no flag B3 opens reads as a loan."""
    return Flag(
        id=f"{conversation}/loan/{amount}",
        kind=FlagKind.DEBT,
        owner=lender,
        about=borrower,
        description=f"a loan of {amount}",
        created=when,
    )


def lent(flag: Flag) -> int | None:
    """What a loan's flag says was lent, or None for any other flag."""
    found = LOAN_ID.search(flag.id) if flag.kind is FlagKind.DEBT else None
    return int(found[1]) if found else None


def owed(rel: Relationship) -> Flag | None:
    """The oldest loan `rel.about` hasn't paid `rel.owner` back."""
    loans = [flag for flag in rel.flags if flag.resolved is None and lent(flag) is not None]
    return min(loans, key=lambda flag: flag.created, default=None)
