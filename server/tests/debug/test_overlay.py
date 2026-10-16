import itertools
import logging

import anyio
import pytest
from pydantic import JsonValue

from simile.debug import Overlay
from simile.protocol import NpcStateMessage, WatchNpcMessage


class Village:
    def __init__(self) -> None:
        self.reads = itertools.count(1)
        self.broken = False

    def npc_state(self, npc: str) -> dict[str, JsonValue] | None:
        if self.broken:
            raise RuntimeError("boom")
        return {"read": next(self.reads)} if npc in ("kofi", "priya") else None


@pytest.fixture
def village() -> Village:
    return Village()


@pytest.fixture
def sent() -> list[NpcStateMessage]:
    return []


@pytest.fixture
def overlay(village: Village, sent: list[NpcStateMessage]) -> Overlay:
    return Overlay(sent.append, village.npc_state)


def watch(npc: str | None) -> WatchNpcMessage:
    return WatchNpcMessage(npc_id=npc)


def test_sends_nothing_until_watching(overlay: Overlay, sent: list[NpcStateMessage]) -> None:
    overlay.send()

    assert sent == []


def test_sends_state_as_soon_as_an_npc_is_watched_and_on_each_send(
    overlay: Overlay, sent: list[NpcStateMessage]
) -> None:
    overlay.watch(watch("kofi"))
    overlay.send()
    overlay.watch(watch("priya"))

    assert sent == [
        NpcStateMessage(npc_id="kofi", state={"read": 1}),
        NpcStateMessage(npc_id="kofi", state={"read": 2}),
        NpcStateMessage(npc_id="priya", state={"read": 3}),
    ]


def test_null_stops_watching(overlay: Overlay, sent: list[NpcStateMessage]) -> None:
    overlay.watch(watch("kofi"))
    overlay.watch(watch(None))
    overlay.send()

    assert [message.state for message in sent] == [{"read": 1}]


def test_stops_watching_someone_who_is_not_an_npc(
    overlay: Overlay, sent: list[NpcStateMessage], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        overlay.watch(watch("player"))
    overlay.send()

    assert sent == []
    assert overlay.watched is None
    assert "no such NPC" in caplog.text


def test_keeps_watching_when_reading_state_fails(
    overlay: Overlay, village: Village, sent: list[NpcStateMessage]
) -> None:
    village.broken = True
    overlay.watch(watch("kofi"))
    village.broken = False
    overlay.send()

    assert [message.state for message in sent] == [{"read": 1}]


@pytest.mark.anyio
async def test_run_carries_on_when_sending_fails(village: Village) -> None:
    sent: list[NpcStateMessage] = []

    def broadcast(message: NpcStateMessage) -> None:
        sent.append(message)
        if len(sent) <= 2:
            raise RuntimeError("client gone")

    overlay = Overlay(broadcast, village.npc_state)
    overlay.watch(watch("kofi"))

    with anyio.move_on_after(0.1):
        await overlay.run(0.01)

    assert len(sent) > 3


@pytest.mark.anyio
async def test_run_sends_every_interval(overlay: Overlay, sent: list[NpcStateMessage]) -> None:
    overlay.watch(watch("kofi"))

    with anyio.move_on_after(0.1):
        await overlay.run(0.01)

    assert len(sent) > 3
