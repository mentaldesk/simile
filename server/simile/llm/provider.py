from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol


class Model(StrEnum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    HAIKU_4_5 = "claude-haiku-4-5"
    HAIKU_5_5 = "claude-haiku-5-5"


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Request:
    messages: tuple[Message, ...]
    system: str
    model: str
    json_schema: dict[str, Any] | None = None
    """The JSON Schema `structured` asks for, for a backend that can hold the reply to it."""


@dataclass(frozen=True)
class RateLimit:
    status: str
    """`allowed`, `allowed_warning` or `rejected`."""
    window: str | None = None
    """Which subscription limit, e.g. `five_hour` or `seven_day`."""
    utilization: float | None = None
    """Fraction of the window used, from 0 to 1."""
    resets_at: int | None = None
    """Unix time when the window resets."""
    windows: dict[str, float] = field(default_factory=dict)
    """Fraction used of every window Claude Code reported, e.g. `five_hour` and `seven_day`."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    """Uncached input tokens. The prompt is these plus the cache reads and writes."""
    output_tokens: int = 0
    """Every token the model wrote, `thinking_tokens` included."""
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None
    """What the call would have cost on the API. The subscription isn't billed per call."""
    model: str | None = None
    """The full name of the model that answered, which an alias like `haiku` resolves to."""
    api_ms: float | None = None
    """Time spent waiting on the model API. The rest of a call's latency is backend overhead."""
    rate_limit: RateLimit | None = None
    """The subscription's usage limit, if the backend reported it during the call."""


class LLMError(Exception):
    pass


class Provider(Protocol):
    """A backend that turns a request into text chunks, then one `Usage` as the last item."""

    name: str

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]: ...
