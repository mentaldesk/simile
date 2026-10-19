import asyncio
import heapq
import itertools
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from simile.llm.provider import Message, Model, Provider, Request, Usage

if TYPE_CHECKING:
    from pydantic import BaseModel, ValidationError

logger = logging.getLogger("simile.llm")

Prompt = str | Sequence[Message]


@dataclass(frozen=True)
class CallRecord:
    purpose: str
    model: str
    provider: str
    started_at: float
    queued_ms: float
    """Time spent waiting for a free slot under the concurrency cap."""
    latency_ms: float
    ttft_ms: float | None
    usage: Usage | None
    error: str | None


class StructuredOutputError(Exception):
    def __init__(self, text: str, error: "ValidationError") -> None:
        super().__init__(f"Reply didn't match the schema after a retry: {error}")
        self.text = text
        self.error = error


class Slots:
    """A concurrency cap that gives a freed slot to the highest priority waiting, then FIFO.
    The last `reserved` free slots only go to calls with a priority above 0."""

    def __init__(self, size: int, reserved: int = 0) -> None:
        self._free = size
        self._reserved = max(0, min(reserved, size - 1))
        self._waiting: list[tuple[int, int, asyncio.Future[None]]] = []
        self._order = itertools.count()

    @asynccontextmanager
    async def hold(self, priority: int) -> AsyncIterator[None]:
        await self._acquire(priority)
        try:
            yield
        finally:
            self._release()

    def _available(self, priority: int) -> bool:
        return self._free > (0 if priority > 0 else self._reserved)

    async def _acquire(self, priority: int) -> None:
        if self._available(priority):
            self._free -= 1
            return
        granted = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiting, (-priority, next(self._order), granted))
        try:
            await granted
        except asyncio.CancelledError:
            if granted.done() and not granted.cancelled():
                self._release()
            raise

    def _release(self) -> None:
        self._free += 1
        while self._waiting:
            priority, _, granted = self._waiting[0]
            if granted.done():
                heapq.heappop(self._waiting)
            elif self._available(-priority):
                heapq.heappop(self._waiting)
                self._free -= 1
                granted.set_result(None)
            else:
                return


class LLMClient:
    def __init__(
        self,
        provider: Provider | None = None,
        *,
        max_concurrency: int = 4,
        reserved: int = 1,
        listeners: Iterable[Callable[[CallRecord], None]] = (),
    ) -> None:
        self._provider = provider
        self._given = provider is not None
        self._ollama: Provider | None = None
        self._slots = Slots(max_concurrency, reserved)
        self.listeners = list(listeners)

    @property
    def provider(self) -> Provider:
        if self._provider is None:
            from simile.llm.claude_code import ClaudeCodeProvider

            self._provider = ClaudeCodeProvider()
        return self._provider

    def provider_for(self, model: str) -> Provider:
        """Ollama for `ollama:<model>`, unless the client was given a provider for everything."""
        from simile.llm.ollama import PREFIX

        if not self._given and model.startswith(PREFIX):
            if self._ollama is None:
                from simile.llm.ollama import OllamaProvider

                self._ollama = OllamaProvider()
            return self._ollama
        return self.provider

    async def stream(
        self,
        prompt: Prompt,
        *,
        system: str = "",
        model: str = Model.HAIKU,
        purpose: str = "",
        priority: int = 0,
        json_schema: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        request = Request(as_messages(prompt), system, str(model), json_schema)
        provider = self.provider_for(request.model)
        queued = time.perf_counter()
        async with self._slots.hold(priority):
            started_at, start = time.time(), time.perf_counter()
            ttft: float | None = None
            end: float | None = None
            usage: Usage | None = None
            error: str | None = None
            try:
                async with aclosing(provider.stream(request)) as chunks:
                    async for chunk in chunks:
                        if isinstance(chunk, Usage):
                            usage, end = chunk, time.perf_counter()
                        elif chunk:
                            if ttft is None:
                                ttft = (time.perf_counter() - start) * 1000
                            yield chunk
            except (GeneratorExit, asyncio.CancelledError):
                error = "cancelled"
                raise
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                raise
            finally:
                self._emit(
                    CallRecord(
                        purpose=purpose,
                        model=request.model,
                        provider=provider.name,
                        started_at=started_at,
                        queued_ms=(start - queued) * 1000,
                        latency_ms=((end or time.perf_counter()) - start) * 1000,
                        ttft_ms=ttft,
                        usage=usage,
                        error=error,
                    )
                )

    def warm(self, *, system: str = "", model: str = Model.HAIKU) -> None:
        """Get the provider ready for a `stream` with this system prompt and model, if it can.
        Claude Code starts a process, which saves its startup on that call."""
        warm = getattr(self.provider_for(str(model)), "warm", None)
        if warm is not None:
            warm(system, str(model))

    async def aclose(self) -> None:
        close = getattr(self._provider, "aclose", None)
        if close is not None:
            await close()

    async def complete(
        self,
        prompt: Prompt,
        *,
        system: str = "",
        model: str = Model.HAIKU,
        purpose: str = "",
        priority: int = 0,
    ) -> str:
        chunks = self.stream(prompt, system=system, model=model, purpose=purpose, priority=priority)
        return "".join([chunk async for chunk in chunks])

    async def structured[T: "BaseModel"](
        self,
        prompt: Prompt,
        schema: type[T],
        *,
        system: str = "",
        model: str = Model.HAIKU,
        purpose: str = "",
        priority: int = 0,
    ) -> T:
        """Ask for JSON matching `schema` and validate it, retrying once with the error."""
        from pydantic import ValidationError

        messages = list(as_messages(prompt))
        system = f"{system}\n\n{json_instructions(schema)}".strip()
        json_schema = schema.model_json_schema()
        for _ in range(2):
            chunks = self.stream(
                messages,
                system=system,
                model=model,
                purpose=purpose,
                priority=priority,
                json_schema=json_schema,
            )
            text = "".join([chunk async for chunk in chunks])
            try:
                return schema.model_validate_json(extract_json(text))
            except ValidationError as e:
                error = e
                messages += [
                    Message("assistant", text),
                    Message(
                        "user",
                        f"That reply didn't match the schema:\n{error}\n\n"
                        "Reply again with only the corrected JSON object.",
                    ),
                ]
        raise StructuredOutputError(text, error) from error

    def _emit(self, record: CallRecord) -> None:
        usage = record.usage or Usage()
        answered = usage.model if usage.model and usage.model != record.model else None
        logger.info(
            "llm %s model=%s latency=%.0fms ttft=%s queued=%.0fms %s%s",
            record.purpose or "call",
            f"{record.model}->{answered}" if answered else record.model,
            record.latency_ms,
            "-" if record.ttft_ms is None else f"{record.ttft_ms:.0f}ms",
            record.queued_ms,
            describe_usage(usage),
            f" error={record.error}" if record.error else "",
            extra={"llm_call": record},
        )
        for listener in self.listeners:
            try:
                listener(record)
            except Exception:
                logger.exception("LLM call listener %r failed", listener)


def describe_usage(usage: Usage) -> str:
    prompt = usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens
    text = (
        f"tokens in={prompt} (cache read {usage.cache_read_tokens}, "
        f"write {usage.cache_creation_tokens}) out={usage.output_tokens} "
        f"(thinking {usage.thinking_tokens})"
    )
    if usage.cost_usd is not None:
        text += f" api_cost=${usage.cost_usd:.5f}"
    if usage.rate_limit is not None:
        text += "".join(f" {name}={used:.0%}" for name, used in usage.rate_limit.windows.items())
    return text


def as_messages(prompt: Prompt) -> tuple[Message, ...]:
    messages = (Message("user", prompt),) if isinstance(prompt, str) else tuple(prompt)
    if not messages or messages[-1].role != "user":
        raise ValueError("The last message must be from the user")
    return messages


def json_instructions(schema: type["BaseModel"]) -> str:
    return (
        "Reply with only a JSON object that matches this JSON Schema, "
        "with no other text and no code fence:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )


def extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text
