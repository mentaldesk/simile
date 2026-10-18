"""Refuses requests another site could make through the player's browser.

SIMILE_HOSTS and SIMILE_ORIGINS add comma-separated host names and origins to the defaults.
"""

import logging
import os
import re
from collections.abc import Callable
from typing import Any, NamedTuple

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.routing import Match
from starlette.status import WS_1008_POLICY_VIOLATION
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

logger = logging.getLogger(__name__)

HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
ORIGINS = frozenset(
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1", "[::1]") for port in (5173, 8000)
)
SAFE_METHODS = frozenset({"GET", "HEAD"})
HOST = re.compile(r"(?:\[(?P<ipv6>[^\]]+)\]|(?P<name>[^:\[\]]+))(?::\d+)?")
MAX_LOGGED = 256
JSON = "application/json"

type MediaTypes = frozenset[str | None]


class Refusal(NamedTuple):
    check: str
    status: int
    reason: str


def accepts[E: Callable[..., Any]](*media_types: str | None) -> Callable[[E], E]:
    """Declares the Content-Types an endpoint takes instead of JSON. None is no Content-Type."""

    def declare(endpoint: E) -> E:
        endpoint.accepts = frozenset(media_types)  # type: ignore[attr-defined]
        return endpoint

    return declare


def host_name(host: str) -> str:
    """`host` without its port: "[::1]:8000" is "::1", and "" if it isn't a host."""
    found = HOST.fullmatch(host.strip().lower())
    return (found["ipv6"] or found["name"]) if found else ""


def media_type(content_type: str | None) -> str | None:
    return None if content_type is None else content_type.partition(";")[0].strip().lower()


def listed(name: str) -> set[str]:
    return {item.strip().lower() for item in os.environ.get(name, "").split(",") if item.strip()}


def expected(scope: Scope) -> MediaTypes | None:
    """What the route for `scope` takes, or None if no route does, for the router to refuse."""
    for route in scope["app"].router.routes:
        match, child = route.matches(scope)
        if match is Match.FULL:
            return getattr(child.get("endpoint"), "accepts", frozenset({JSON}))
    return None


def wanted(media_types: MediaTypes, given: str | None) -> str:
    named = " or ".join(sorted(media for media in media_types if media))
    asked = f"Send the request as {named}" if named else "This request takes no body"
    return asked if given is None else f"{asked}, not {given or 'an empty Content-Type'}"


class Guard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.hosts = HOSTS | {host_name(host) or host for host in listed("SIMILE_HOSTS")}
        self.origins = ORIGINS | {origin.rstrip("/") for origin in listed("SIMILE_ORIGINS")}
        self.logged: set[tuple[str, str]] = set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        refusal = self.refusal(scope, headers)
        if refusal is None:
            await self.app(scope, receive, send)
            return
        source = headers.get("origin") or headers.get("host") or "a request with no Host"
        if (refusal.check, source) not in self.logged and len(self.logged) < MAX_LOGGED:
            self.logged.add((refusal.check, source))
            method = scope.get("method", "WebSocket")
            logger.warning(f"Refused {method} {scope['path']} from {source}: {refusal.reason}")
        if scope["type"] == "websocket":
            await WebSocketClose(WS_1008_POLICY_VIOLATION, refusal.reason)(scope, receive, send)
        else:
            response = JSONResponse({"error": refusal.reason}, status_code=refusal.status)
            await response(scope, receive, send)

    def refusal(self, scope: Scope, headers: Headers) -> Refusal | None:
        if host_name(headers.get("host", "")) not in self.hosts:
            return Refusal("host", 403, "This server only answers to localhost")
        if scope["type"] == "http" and scope["method"] in SAFE_METHODS:
            return None
        origin = headers.get("origin")
        if origin is not None and origin.lower() not in self.origins:
            return Refusal("origin", 403, "Requests from other sites aren't allowed")
        if scope["type"] == "websocket":
            return None
        media_types, given = expected(scope), media_type(headers.get("content-type"))
        if media_types is None or given in media_types:
            return None
        return Refusal("content type", 415, wanted(media_types, given))
