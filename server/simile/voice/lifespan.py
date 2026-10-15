import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    if os.environ.get("SIMILE_VOICE") != "1" or getattr(app.state, "headless", False):
        yield
        return
    try:
        from simile.voice.qwen import QwenSynthesiser
    except ImportError:
        logger.warning("SIMILE_VOICE=1 but the voice extra isn't installed, so running unvoiced")
        yield
        return
    from simile.voice.service import VoiceService

    started = time.perf_counter()
    async with VoiceService(QwenSynthesiser()) as voice:
        logger.info(f"Loaded the voice model in {time.perf_counter() - started:.1f}s")
        app.state.voice = voice
        yield
