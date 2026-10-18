from datetime import UTC, datetime, timedelta

from simile.npc import load_npcs
from simile.schema import Flag, FlagKind
from simile.social import describe, lent, loan, meet, open_flag, owed, resolve_flag

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
BEN = load_npcs()[0].model_copy(update={"id": "ben"})


def test_a_loan_is_a_debt_the_lender_holds_about_the_borrower() -> None:
    flag = loan("ben", "ana", 60, "talk_1", NOW)

    assert (flag.kind, flag.owner, flag.about) == (FlagKind.DEBT, "ben", "ana")
    assert flag.description == "a loan of 60"
    assert lent(flag) == 60
    rel = open_flag(meet(BEN, "ana"), flag)
    assert describe(rel, "Ana").endswith("Ana still owes you for a loan of 60.")


def test_only_a_loans_own_flag_says_what_was_lent() -> None:
    told = Flag(
        id="talk_1/1",
        kind=FlagKind.DEBT,
        owner="ben",
        about="ana",
        description="a loan of 60",
        created=NOW,
    )
    promised = loan("ben", "ana", 60, "talk_1", NOW).model_copy(update={"kind": FlagKind.PROMISE})

    assert lent(told) is None
    assert lent(promised) is None


def test_owed_is_the_oldest_loan_not_yet_paid_back() -> None:
    first = loan("ben", "ana", 60, "talk_1", NOW)
    second = loan("ben", "ana", 30, "talk_2", NOW + timedelta(days=1))
    favour = Flag(
        id="talk_3/1",
        kind=FlagKind.DEBT,
        owner="ben",
        about="ana",
        description="a lift",
        created=NOW,
    )
    rel = meet(BEN, "ana")
    for flag in (second, favour, first):
        rel = open_flag(rel, flag)

    assert owed(meet(BEN, "ana")) is None
    assert owed(rel) == first
    assert owed(resolve_flag(rel, first.id, NOW)) == second
