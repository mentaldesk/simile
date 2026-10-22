from collections.abc import Callable

import pytest

from simile.player.sync import PlayerSync
from simile.protocol import Meal, PlayerStateMessage
from simile.schema import SOLD, Item, ItemKind, MapTile, Pile, Player, lamp

HOME = Meal(place="maker_space", name="home", price=0)
BUN = Item(id="pork_bun", kind=ItemKind.FOOD, name="Pork bun", weight=0.2)


class Sent:
    def __init__(self, player: Player) -> None:
        self.messages: list[PlayerStateMessage] = []
        self.meal: Meal | None = None
        self.sync = PlayerSync(player, lambda: self.meal, self.messages.append)

    def after(self, change: Callable[[], object]) -> list[PlayerStateMessage]:
        change()
        self.sync.tick(0.1)
        sent = list(self.messages)
        self.messages.clear()
        return sent


def test_new_clients_are_greeted_with_the_player_and_the_meal_on_offer() -> None:
    player, sent = Player(hunger=0.3), []
    sync = PlayerSync(player, lambda: HOME, sent.append)

    sync.update()

    assert sent == []
    assert sync.message() == PlayerStateMessage(player=player, meal=HOME)


def test_it_sends_a_copy_that_later_changes_leave_alone() -> None:
    player = Player()
    sent = Sent(player)
    [message] = sent.after(lambda: setattr(player, "money", 30))

    player.money = 40

    assert message.player.money == 30


def test_nothing_is_sent_while_nothing_changes() -> None:
    sent = Sent(Player())

    assert sent.after(lambda: None) == []


def test_a_change_to_hunger_alone_waits_until_it_has_moved_a_hundredth() -> None:
    player = Player(hunger=0.5)
    sent = Sent(player)

    assert sent.after(lambda: setattr(player, "hunger", 0.505)) == []
    assert sent.after(lambda: setattr(player, "hunger", 0.5099)) == []
    [message] = sent.after(lambda: setattr(player, "hunger", 0.51))
    assert message.player.hunger == 0.51
    assert sent.after(lambda: setattr(player, "hunger", 0.515)) == []
    assert len(sent.after(lambda: setattr(player, "hunger", 0.5))) == 1


def test_a_lamps_charge_alone_waits_too() -> None:
    player = Player()
    sent = Sent(player)

    assert sent.after(lambda: setattr(player.items[0], "charge", 0.995)) == []
    [message] = sent.after(lambda: setattr(player.items[0], "charge", 0.99))
    assert message.player.items[0].charge == 0.99


@pytest.mark.parametrize(
    "change",
    [
        lambda player, sent: setattr(player, "money", 0.01),
        lambda player, sent: setattr(player, "items", [*player.items, BUN]),
        lambda player, sent: setattr(player, "items", []),
        lambda player, sent: setattr(player.items[0], "on", True),
        lambda player, sent: setattr(player.body, "left_kidney", SOLD),
        lambda player, sent: setattr(
            player, "left", [Pile(at=MapTile(map="kapok_walk", x=1, y=15), items=[BUN])]
        ),
        lambda player, sent: setattr(sent, "meal", HOME),
    ],
    ids=["money", "an_item", "dropping_everything", "a_switch", "the_body", "a_pile", "a_meal"],
)
def test_any_other_change_is_sent_at_once(change: Callable[[Player, Sent], None]) -> None:
    player = Player(hunger=0.5)
    sent = Sent(player)

    [message] = sent.after(lambda: change(player, sent))

    assert message == PlayerStateMessage(player=player, meal=sent.meal)


def test_with_a_change_it_sends_hunger_as_it_is() -> None:
    player = Player(hunger=0.5)
    sent = Sent(player)
    player.hunger = 0.503

    [message] = sent.after(lambda: setattr(player, "items", [lamp(), BUN]))

    assert message.player.hunger == 0.503
    assert sent.after(lambda: setattr(player, "hunger", 0.51)) == []
