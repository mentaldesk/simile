import functools
import os
from collections.abc import Awaitable, Callable
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from simile.news.feed import SCHEMES, Feed, FeedRefused, Fetched, fetch, override
from simile.news.feed_list import Refused, SavedFeed, feed_list_of
from simile.news.refresh import MAX_PER_FEED
from simile.news.store import news_of

MAX_BODY = 4 * 1024
MAX_URL = 2048
MAX_NAME = 80

type Endpoint = Callable[[Request], Awaitable[Response]]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Listed(Body):
    url: str = Field(max_length=MAX_URL)


class FeedUrl(Listed):
    @field_validator("url")
    @classmethod
    def http(cls, url: str) -> str:
        url = url.strip()
        parts = urlsplit(url)
        if parts.scheme.lower() not in SCHEMES:
            raise PydanticCustomError("feed_url", "Paste a URL that starts with http or https")
        if any(c.isspace() or not c.isprintable() for c in url):
            raise PydanticCustomError("feed_url", "A URL can't have spaces in it")
        if not parts.hostname:
            raise PydanticCustomError("feed_url", "The URL needs a site's name after the //")
        if parts.username or parts.password:
            raise PydanticCustomError("feed_url", "Leave the user name and password out")
        try:
            _ = parts.port
        except ValueError:
            raise PydanticCustomError("feed_url", "That URL's port isn't a valid one") from None
        return url


class Switch(Listed):
    on: bool = Field(strict=True)


def guarded(endpoint: Endpoint) -> Endpoint:
    @functools.wraps(endpoint)
    async def respond(request: Request) -> Response:
        try:
            return await endpoint(request)
        except Refused as error:
            return JSONResponse({"error": str(error)}, status_code=error.status)
        except ValidationError as error:
            return JSONResponse({"error": _reasons(error)}, status_code=422)

    return respond


async def body[T: Body](request: Request, model: type[T]) -> T:
    """The request's JSON body as `model`. Only JSON, so another site's form can't post it."""
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind != "application/json":
        raise Refused(415, "Send the request as JSON")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BODY:
            raise Refused(413, f"The request can be at most {MAX_BODY // 1024} KB")
    return model.model_validate_json(bytes(data) or b"{}")


def listing(app: Starlette) -> dict[str, Any]:
    feed_list, store = feed_list_of(app), news_of(app)
    overridden = override()
    return {
        "feeds": [
            {**saved.model_dump(), "checked": store.feed(saved.url).checked}
            for saved in feed_list.feeds
        ],
        "defaults": feed_list.defaults,
        "override": [feed.url for feed in overridden] if overridden else None,
        "fetching": os.environ.get("SIMILE_NEWS") != "0",
        "max": feed_list.limit,
        "calls_per_feed": MAX_PER_FEED,
    }


async def fetched(url: str) -> Fetched:
    """`url` fetched once, or refused with the reason in words for the player."""
    try:
        return await run_in_threadpool(fetch, Feed(url))
    except FeedRefused as error:
        raise Refused(422, str(error)) from None
    except HTTPError as error:
        raise Refused(422, f"The site answered {error.code} {error.reason}") from None
    except URLError as error:
        raise Refused(422, f"Couldn't reach it: {error.reason}") from None
    except TimeoutError:
        raise Refused(422, "It took too long to answer") from None
    except (OSError, HTTPException) as error:
        raise Refused(422, f"Couldn't read it: {error or type(error).__name__}") from None


def preview(url: str, feed: Fetched) -> dict[str, Any]:
    latest = max(feed.items or [], key=lambda item: item.published, default=None)
    headline = None
    if latest:
        headline = {"title": latest.title, "published": latest.published.isoformat()}
    return {"url": url, "title": feed.title, "latest": headline}


@guarded
async def show(request: Request) -> Response:
    return JSONResponse(listing(request.app))


@guarded
async def check(request: Request) -> Response:
    url = (await body(request, FeedUrl)).url
    feed_list_of(request.app).check(url)
    return JSONResponse(preview(url, await fetched(url)))


@guarded
async def add(request: Request) -> Response:
    url = (await body(request, FeedUrl)).url
    feed_list = feed_list_of(request.app)
    feed_list.check(url)
    feed = await fetched(url)
    name = feed.title[:MAX_NAME].strip() or urlsplit(url).hostname or url
    feed_list.add(SavedFeed(url=url, name=name))
    return JSONResponse(listing(request.app), status_code=201)


@guarded
async def switch(request: Request) -> Response:
    asked = await body(request, Switch)
    feed_list_of(request.app).switch(asked.url, asked.on)
    return JSONResponse(listing(request.app))


@guarded
async def remove(request: Request) -> Response:
    feed_list_of(request.app).remove((await body(request, Listed)).url)
    return JSONResponse(listing(request.app))


@guarded
async def reset(request: Request) -> Response:
    await body(request, Body)
    feed_list_of(request.app).reset()
    return JSONResponse(listing(request.app))


def _reasons(error: ValidationError) -> str:
    return "; ".join(
        e["msg"] if e["type"] == "feed_url" or not e["loc"] else f"{e['loc'][0]}: {e['msg']}"
        for e in error.errors(include_url=False)
    )


routes: list[BaseRoute] = [
    Route("/api/news/feeds", show, methods=["GET"]),
    Route("/api/news/feeds", add, methods=["POST"]),
    Route("/api/news/feeds/check", check, methods=["POST"]),
    Route("/api/news/feeds/switch", switch, methods=["POST"]),
    Route("/api/news/feeds/remove", remove, methods=["POST"]),
    Route("/api/news/feeds/reset", reset, methods=["POST"]),
]
