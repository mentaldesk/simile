import logging
from collections.abc import Callable
from typing import Any

from simile.sim.events import Event

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[tuple[type[Event], Callable[[Any], None]]] = []

    def subscribe[E: Event](
        self, event_type: type[E], handler: Callable[[E], None]
    ) -> Callable[[], None]:
        subscriber = (event_type, handler)
        self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            self._subscribers = [other for other in self._subscribers if other is not subscriber]

        return unsubscribe

    def publish(self, event: Event) -> None:
        for event_type, handler in tuple(self._subscribers):
            if isinstance(event, event_type):
                try:
                    handler(event)
                except Exception:
                    logger.exception("%r failed to handle %r", handler, event)
