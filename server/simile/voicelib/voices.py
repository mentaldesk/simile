"""The voice library: the residents' clips in `content/voices/`, tagged in `library.json`."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field, TypeAdapter

from simile.schema import Gender, Id, Model

VOICES = Path(__file__).resolve().parents[3] / "content" / "voices"
LIBRARY = VOICES / "library.json"


class Age(StrEnum):
    YOUNG = "young"
    MIDDLE_AGED = "middle-aged"
    OLDER = "older"


class Tags(Model):
    accent: str = Field(min_length=1)
    age: Age
    gender: Gender


class LibraryVoice(Tags):
    id: Id
    reference_line: str
    clip: str


class UnknownVoice(LookupError):
    pass


TAGGED = TypeAdapter(dict[Id, Tags])


def tags() -> dict[str, Tags]:
    return TAGGED.validate_json(LIBRARY.read_bytes())


def voices() -> list[LibraryVoice]:
    return [
        LibraryVoice(
            id=id, reference_line=transcript(id), clip=f"/api/voices/{id}/clip", **tag.model_dump()
        )
        for id, tag in tags().items()
    ]


def clip_path(id: str) -> Path:
    if id not in tags():
        raise UnknownVoice(f"There's no {id!r} voice in the library")
    return VOICES / f"{id}.wav"


def transcript(id: str) -> str:
    return " ".join(clip_path(id).with_suffix(".txt").read_text(encoding="utf-8").split())
