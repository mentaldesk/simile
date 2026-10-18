import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import asdict, replace
from typing import Any

import anyio
from pydantic import Field, ValidationError, field_validator

from simile.characters.brief import SECTIONS
from simile.characters.generate import Generated
from simile.library.archive import reasons
from simile.library.store import Library
from simile.llm import LLMClient, LLMError, StructuredOutputError
from simile.schema import Character, Model

logger = logging.getLogger(__name__)

MAX_GENERATING = 2

type Send = Callable[[dict[str, Any]], None]
type Work = Callable[[LLMClient], Awaitable[Generated]]


class Reroll(Model):
    character: Character
    sections: list[str] = Field(min_length=1)

    @field_validator("sections")
    @classmethod
    def _known(cls, sections: list[str]) -> list[str]:
        if unknown := set(sections) - set(SECTIONS):
            raise ValueError(f"no such section: {', '.join(sorted(unknown))}")
        return sections


class Streaming(LLMClient):
    """`llm`, also sending each call's purpose and text to `send` as it streams."""

    def __init__(self, llm: LLMClient, send: Send) -> None:
        super().__init__()
        self._llm, self._send = llm, send

    async def stream(self, prompt: Any, *, purpose: str = "", **options: Any) -> AsyncIterator[str]:
        self._send({"type": "call", "purpose": purpose})
        async with aclosing(self._llm.stream(prompt, purpose=purpose, **options)) as chunks:
            async for chunk in chunks:
                self._send({"type": "text", "text": chunk})
                yield chunk


async def events(library: Library, llm: LLMClient, work: Work) -> AsyncIterator[str]:
    """NDJSON lines: each call and its text as it streams, then `done` or `error`."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def run() -> None:
        try:
            generated = await checked(library, await work(Streaming(llm, queue.put_nowait)))
            queue.put_nowait(done(generated))
        except (LLMError, StructuredOutputError) as error:
            queue.put_nowait({"type": "error", "error": str(error)})
        except ValidationError as error:
            queue.put_nowait({"type": "error", "error": reasons(error)})
        except Exception as error:
            logger.exception("Couldn't generate a character")
            queue.put_nowait({"type": "error", "error": f"{type(error).__name__}: {error}"})
        finally:
            queue.put_nowait(None)

    library.generating += 1
    task = asyncio.create_task(run())
    try:
        while (event := await queue.get()) is not None:
            yield json.dumps(event) + "\n"
    finally:
        library.generating -= 1
        task.cancel()


async def checked(library: Library, generated: Generated) -> Generated:
    """`generated`, warned if it's a near-copy of a library character."""
    try:
        match = await anyio.to_thread.run_sync(
            library.too_close, generated.character, abandon_on_cancel=True
        )
    except Exception as error:
        logger.warning("Couldn't check a new character against the library: %s", error)
        warning = f"Couldn't check how close it is to the library: {error}"
        return replace(generated, warnings=[*generated.warnings, warning])
    if match is None:
        return generated
    warning = f"Close to {match.name} in the library ({match.similarity:.2f})."
    return replace(generated, warnings=[*generated.warnings, warning])


def done(generated: Generated) -> dict[str, Any]:
    return {
        "type": "done",
        "character": generated.character.model_dump(mode="json"),
        "suggestions": [asdict(suggestion) for suggestion in generated.suggestions],
        "notes": generated.notes,
        "warnings": generated.warnings,
    }
