from typing import TYPE_CHECKING

from simile.economy.ledger import Kind
from simile.schema import Id

if TYPE_CHECKING:
    from simile.economy.economy import Economy


def transfer(economy: "Economy", payer: Id, payee: Id, amount: float, kind: Kind) -> bool:
    """Hand money from one resident to another through the ledger, if the payer holds it."""
    money = economy.money
    if payer == payee or payer not in money or payee not in money:
        return False
    if not 0 < amount <= money[payer]:
        return False
    economy.pay(payer, payee, amount, kind)
    return True
