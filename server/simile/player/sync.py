from collections.abc import Callable

from simile.player.config import DEFAULT_CONFIG
from simile.protocol import Buyer, Meal, PlayerStateMessage
from simile.schema import Pile, Player


class PlayerSync:
    """Sends `player_state` on each change, and on hunger or charge alone once moved by `step`."""

    def __init__(
        self,
        player: Player,
        meal: Callable[[], Meal | None],
        send: Callable[[PlayerStateMessage], None],
        step: float = DEFAULT_CONFIG.step,
        *,
        buyer: Callable[[], Buyer | None] = lambda: None,
        piles: Callable[[], list[Pile]] = list,
    ) -> None:
        self.player = player
        self.meal = meal
        self.send = send
        self.step = step
        self.buyer = buyer
        self.piles = piles
        self.sent = self.message()

    def message(self) -> PlayerStateMessage:
        return PlayerStateMessage(
            player=self.player.model_copy(deep=True),
            meal=self.meal(),
            buyer=self.buyer(),
            piles=self.piles(),
        )

    def tick(self, dt: float) -> None:
        self.update()

    def update(self) -> None:
        """Sends the player's state if it's changed enough since it was last sent."""
        message = self.message()
        if self._changed(self.sent, message):
            self.send(message)
            self.sent = message

    def _changed(self, old: PlayerStateMessage, new: PlayerStateMessage) -> bool:
        if _steady(old) != _steady(new):
            return True
        moved = zip(_moving(old), _moving(new), strict=True)
        return any(abs(a - b) >= self.step - 1e-9 for a, b in moved)


def _moving(message: PlayerStateMessage) -> list[float]:
    player = message.player
    return [player.hunger, *(item.charge for item in player.items if item.charge is not None)]


def _steady(message: PlayerStateMessage) -> PlayerStateMessage:
    """Without hunger or the lamps' charges, for comparing."""
    player = message.player
    items = [item.model_copy(update={"charge": None}) for item in player.items]
    still = player.model_copy(update={"hunger": 0.0, "items": items})
    return message.model_copy(update={"player": still})
