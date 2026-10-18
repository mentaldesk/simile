"""*Try it*: a character saying any line, through the server's voice service."""

import io
import wave
from contextlib import aclosing
from pathlib import Path

from starlette.applications import Starlette

from simile.schema import Character, Voice
from simile.voice.service import Priority, VoiceService

SAMPLE_RATE = 24_000


class Speaker:
    """Gives the voice service each character's clip once, and again when it changes."""

    def __init__(self) -> None:
        self._added: dict[str, tuple[object, ...]] = {}

    async def say(self, voice: VoiceService, character: Character, clip: Path, line: str) -> bytes:
        key = f"try/{character.id}"
        stat = clip.stat()
        version = (str(clip), stat.st_mtime_ns, stat.st_size, character.voice.reference_line)
        if self._added.get(key) != version or not voice.has_voice(key):
            reference = Voice(
                description=character.voice.description,
                reference_line=character.voice.reference_line,
                # Absolute, since a player character's clip isn't under the repository.
                reference_clip=str(clip.resolve()),
            )
            await voice.add_voice(key, reference)
            self._added[key] = version
        pcm = bytearray()
        async with aclosing(voice.speak(key, line, Priority.PLAYER)) as speech:
            async for chunk in speech:
                pcm += chunk
        return wav(bytes(pcm))


def wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(pcm)
    return buffer.getvalue()


def speaker_of(app: Starlette) -> Speaker:
    if not hasattr(app.state, "try_it"):
        app.state.try_it = Speaker()
    return app.state.try_it
