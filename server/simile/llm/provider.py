from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol


class Model(StrEnum):
    HAIKU = "haiku"
    SONNET = "sonnet"


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Request:
    messages: tuple[Message, ...]
    system: str
    model: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None
    """What the call would have cost on the API. The subscription isn't billed per call."""
    model: str | None = None
    """The model that actually answered, e.g. `claude-haiku-4-5` for `haiku`."""
    api_ms: float | None = None
    """Time spent waiting on the model API. The rest of a call's latency is backend overhead."""


class LLMError(Exception):
    pass


class Provider(Protocol):
    """A backend that turns a request into text chunks, then one `Usage` as the last item."""

    name: str

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]: ...
