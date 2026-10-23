"""ElevenLabs, which says prerecorded clips such as greetings at build time, never live dialogue."""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx
import numpy as np

from simile.voicing import speak
from simile.voicing.greetings import files

API = "https://api.elevenlabs.io"
MODEL = "eleven_v4"
ENV = "ELEVENLABS_API_KEY"
KEYCHAIN = "elevenlabs-api-key"
TIMEOUT = 60.0
KEYCHAIN_TIMEOUT = 2.0
"""Seconds to wait for the Keychain, which may be stuck on a prompt nobody sees."""
NARRATION = "narrative_story"
SHORTLIST = 3
VISIBLE = re.compile(r"[!-~]+")

logger = logging.getLogger(__name__)


class Refused(RuntimeError):
    pass


def _keychain(
    *flags: str, timeout: float = KEYCHAIN_TIMEOUT
) -> subprocess.CompletedProcess[str] | None:
    if shutil.which("security") is None:
        return None
    command = ["security", "find-generic-password", "-s", KEYCHAIN, *flags]
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def _usable(key: str, where: str) -> str | None:
    """The key, or None if it's anything but visible ASCII, which an error could then quote."""
    if VISIBLE.fullmatch(key):
        return key
    logger.warning(
        f"The ElevenLabs key in {where} has a space or control character, so it's unused"
    )
    return None


def configured() -> bool:
    """Whether there's a key, without reading the Keychain's secret."""
    if key := os.environ.get(ENV, "").strip():
        return _usable(key, ENV) is not None
    found = _keychain()
    return found is not None and found.returncode == 0


def api_key(timeout: float = KEYCHAIN_TIMEOUT) -> str | None:
    """`ELEVENLABS_API_KEY`, or the Keychain item `elevenlabs-api-key`. Never print or log it."""
    if key := os.environ.get(ENV, "").strip():
        return _usable(key, ENV)
    found = _keychain("-w", timeout=timeout)
    if found is None or found.returncode != 0 or not found.stdout.strip():
        return None
    return _usable(found.stdout.strip(), f"the Keychain item {KEYCHAIN}")


def safely(error: BaseException, key: str | None) -> str:
    """What to say about an error: a refusal's reason without the key, or else only its type."""
    if not isinstance(error, Refused):
        return f"{type(error).__name__} while talking to ElevenLabs"
    said = str(error)
    if key:
        for form in {key, repr(key)[1:-1], repr(key.encode())[2:-1]}:
            said = said.replace(form, "[key]")
    return said


class ElevenLabs:
    """Says lines in library voices with `MODEL`, and counts the credits they cost."""

    def __init__(
        self, key: str, base: str | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(
            base_url=base or API,
            headers={"xi-api-key": key},
            timeout=TIMEOUT,
            transport=transport,
        )
        self.credits = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._http.close()

    def say(self, voice: str, text: str, seed: int) -> Any:
        """Float samples at `speak.SAMPLE_RATE`."""
        response = self._http.post(
            f"/v1/text-to-speech/{voice}",
            params={"output_format": f"pcm_{speak.SAMPLE_RATE}"},
            json={"text": text, "model_id": MODEL, "seed": seed},
        )
        _check(response)
        self.credits += int(response.headers.get("character-cost", len(text)))
        return np.frombuffer(response.content, dtype="<i2").astype(np.float32) / 32768

    def voices(self, **filters: str) -> list[dict[str, Any]]:
        """The voice library's English voices that match `filters`, as the API lists them."""
        response = self._http.get(
            "/v1/shared-voices",
            params={"page_size": "30", "language": "en", "sort": "cloned_by_count", **filters},
        )
        _check(response)
        return response.json()["voices"]

    def choose(
        self, id: str, gender: str | None, age: str, places: Iterable[str]
    ) -> dict[str, Any] | None:
        """A library voice for a new character: their accent or origin, gender and age."""
        who = {"gender": gender} if gender else {}
        for place in [*places, ""]:
            for filters in ({**who, "age": age}, who):
                if place:
                    found = [
                        *self.voices(accent=place.lower(), **filters),
                        *_naming(place, self.voices(search=place, **filters)),
                    ]
                else:
                    found = self.voices(use_cases=NARRATION, **filters)
                if found:
                    ranked = sorted(found, key=lambda voice: voice.get("use_case") != NARRATION)
                    shortlist = list({voice["voice_id"]: voice for voice in ranked}.values())
                    return shortlist[zlib.crc32(id.encode()) % min(SHORTLIST, len(shortlist))]
        return None


def _naming(place: str, voices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The voices whose name, accent or description says `place`, since search is fuzzy."""
    said = re.compile(rf"\b{re.escape(place)}\b", re.IGNORECASE)
    return [
        voice
        for voice in voices
        if said.search(" ".join(str(voice.get(k) or "") for k in ("name", "accent", "description")))
    ]


def _check(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = response.text[:200]
    message = detail.get("message", detail) if isinstance(detail, dict) else detail
    raise Refused(f"ElevenLabs answered {response.status_code}: {message}")


def greeting(audio: Any) -> Any:
    return speak.level(speak.trimmed(audio))


def speaking(eleven: ElevenLabs, voice: str) -> Callable[[str, int], Any]:
    """Says a text with a seed in the library voice, as a greeting."""
    return lambda text, seed: greeting(eleven.say(voice, text, seed))


class FakeElevenLabs(ElevenLabs):
    """ElevenLabs for tests, by the same requests: each line is a tone, the library `voices`."""

    def __init__(self, key: str = "fake", voices: Iterable[Mapping[str, Any]] = ()) -> None:
        super().__init__(key, transport=httpx.MockTransport(self._answer))
        self.library = [dict(voice) for voice in voices]
        self.said: list[tuple[str, str, int]] = []
        self.searched: list[dict[str, str]] = []

    def __exit__(self, *args: Any) -> None:
        pass

    def _answer(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v1/text-to-speech/"):
            asked = json.loads(request.content)
            self.said.append((request.url.path.rsplit("/", 1)[1], asked["text"], asked["seed"]))
            tone = np.sin(np.linspace(0, 2 * np.pi * 200, speak.SAMPLE_RATE))
            pcm = (0.3 * 32767 * tone).astype("<i2").tobytes()
            return httpx.Response(200, content=pcm, headers={"character-cost": "7"})
        filters = dict(request.url.params)
        self.searched.append(filters)
        found = [
            voice
            for voice in self.library
            if all(
                str(voice.get(field, "")) == filters[name]
                for name, field in (("accent", "accent"), ("gender", "gender"), ("age", "age"))
                if name in filters
            )
            and filters.get("use_cases", voice.get("use_case")) == voice.get("use_case")
            and filters.get("search", "").lower() in json.dumps(voice).lower()
        ]
        return httpx.Response(200, json={"voices": found})


AGES = ((35, "young"), (60, "middle_aged"))
GENDERS = {"woman": "female", "man": "male"}
ACCENT = re.compile(r"((?:[A-Z][\w'-]*\s)*[A-Z][\w'-]*)\s+(?:accent|English)\b")


def age_band(age: int) -> str:
    return next((band for under, band in AGES if age < under), "old")


def places(description: str, origin: str) -> list[str]:
    """Where a voice description says the accent is from, then the character's origin."""
    named = [
        " ".join(word for word in found.split() if word not in {"A", "An", "The"})
        for found in ACCENT.findall(description)
    ]
    return list(dict.fromkeys(place for place in [*named, origin] if place))


def say_all(
    eleven: ElevenLabs,
    voice: str,
    id: str,
    delivery: str,
    lines: Sequence[str],
    out: Path,
    progress: speak.Progress | None = None,
) -> list[float]:
    """Writes `<id>_<n>.m4a` in `out` for each line, and returns their lengths."""
    say = speaking(eleven, voice)
    seconds = []
    for n, text in enumerate(lines, 1):
        if progress:
            progress((n - 1) / len(lines), f"Saying greeting {n} of {len(lines)}")
        audio = say(f"{delivery} {text}".strip(), speak.seed(0, id, text))
        speak.encode(audio, out / f"{id}_{n}.m4a")
        seconds.append(round(len(audio) / speak.SAMPLE_RATE, 2))
    return seconds


def main(argv: Iterable[str] | None = None) -> None:
    """The greetings job with ElevenLabs: reads `greetings.json` in its work directory."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("work", type=Path)
    work = parser.parse_args(None if argv is None else list(argv)).work
    asked: Mapping[str, Any] = json.loads((work / "greetings.json").read_text(encoding="utf-8"))
    id, said = asked["voice"], Path(asked["said"])
    if before := files(said, id):
        for path in before:
            shutil.copyfile(path, work / path.name)
        spoken = json.loads((said / "spoken.json").read_text(encoding="utf-8")) | {"credits": 0}
        (work / "spoken.json").write_text(json.dumps(spoken), encoding="utf-8")
        speak.report(1.0, "Said in this voice before")
        return
    key = api_key()
    if key is None:
        sys.exit(f"No usable ElevenLabs key: set {ENV} or add the Keychain item {KEYCHAIN}")
    speak.report(0.0, "Choosing a voice")
    try:
        with ElevenLabs(key) as eleven:
            voice = asked["elevenlabs"] or eleven.choose(
                id, asked["gender"], asked["age"], asked["places"]
            )
            if voice is None:
                sys.exit("ElevenLabs has no voice for them")
            seconds = say_all(
                eleven, voice["voice_id"], id, asked["delivery"], asked["lines"], work, speak.report
            )
    except Exception as error:
        sys.exit(f"Stopped: {safely(error, key)}")
    spoken = {"seconds": seconds, "voice": voice["name"], "credits": eleven.credits}
    (work / "spoken.json").write_text(json.dumps(spoken), encoding="utf-8")
    keep(said, [*files(work, id), work / "spoken.json"])
    speak.report(1.0, "Said")


def keep(folder: Path, paths: Iterable[Path]) -> None:
    """Copies the paths into `folder` all at once, so a killed job leaves it whole or absent."""
    folder.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(dir=folder.parent, prefix=f".{folder.name}."))
    try:
        for path in paths:
            shutil.copyfile(path, scratch / path.name)
        if not folder.exists():
            os.replace(scratch, folder)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
