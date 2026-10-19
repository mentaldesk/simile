import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from simile.llm.provider import LLMError, Request, Usage

PREFIX = "ollama:"
HOST_ENV = "OLLAMA_HOST"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434


class OllamaProvider:
    """Text generation through a local Ollama server's `/api/chat`, for models named
    `ollama:<model>`."""

    name = "ollama"

    def __init__(self, host: str | None = None, *, timeout: float = 300) -> None:
        self.host = base_url(host or os.environ.get(HOST_ENV) or DEFAULT_HOST)
        self.timeout = httpx.Timeout(timeout, connect=5)

    def body(self, request: Request) -> dict[str, Any]:
        system = [{"role": "system", "content": request.system}] if request.system else []
        body: dict[str, Any] = {
            "model": request.model.removeprefix(PREFIX),
            "messages": system + [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": True,
            "think": False,
        }
        if request.json_schema is not None:
            body["format"] = request.json_schema
        return body

    async def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        try:
            async with (
                httpx.AsyncClient(base_url=self.host, timeout=self.timeout) as client,
                client.stream("POST", "/api/chat", json=self.body(request)) as response,
            ):
                if response.status_code != 200:
                    await response.aread()
                    raise LLMError(f"Ollama: {error_of(response)}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    frame = json.loads(line)
                    if "error" in frame:
                        raise LLMError(f"Ollama: {frame['error']}")
                    if text := frame.get("message", {}).get("content"):
                        yield text
                    if frame.get("done"):
                        if frame.get("done_reason") == "length":
                            raise LLMError("Ollama cut the reply short at its length limit")
                        yield usage_from(frame)
                        return
            raise LLMError("Ollama ended the reply before it was done")
        except httpx.ConnectError as e:
            raise LLMError(f"Can't reach Ollama at {self.host}. Is it running?") from e
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            raise LLMError(f"Ollama: {type(e).__name__}: {e}") from e


def base_url(host: str) -> str:
    """`OLLAMA_HOST` as Ollama reads it: without a scheme, the port defaults to 11434."""
    if "://" in host:
        return host.rstrip("/")
    url = httpx.URL(f"http://{host}")
    return str(url.copy_with(port=url.port or DEFAULT_PORT)).rstrip("/")


def error_of(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"])
    except (ValueError, KeyError, TypeError):
        return f"HTTP {response.status_code} {response.text[:200]}".strip()


def usage_from(frame: dict[str, Any]) -> Usage:
    prompt = frame.get("prompt_eval_count", 0)
    cached = frame.get("prompt_eval_cached_count", 0)
    return Usage(
        input_tokens=prompt - cached,
        output_tokens=frame.get("eval_count", 0),
        cache_read_tokens=cached,
        model=f"{PREFIX}{frame['model']}" if "model" in frame else None,
        api_ms=frame["total_duration"] / 1e6 if "total_duration" in frame else None,
    )
