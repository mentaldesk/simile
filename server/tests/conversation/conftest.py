from collections.abc import Sequence
from datetime import datetime

from simile.schema import CoreValue, Medium, Memory, MemoryKind, Work


def work(
    id: str,
    artist: str,
    title: str,
    created: datetime,
    *,
    medium: Medium = Medium.MURAL,
    tags: Sequence[str] = (),
    values: dict[CoreValue, float] | None = None,
) -> Work:
    return Work(
        id=id,
        artist=artist,
        medium=medium,
        form="bright murals" if medium is Medium.MURAL else "plain verse",
        title=title,
        created=created,
        text="A red planet over the rooftops.",
        statement="Mars is for everyone.",
        inspired_by=[],
        values={**dict.fromkeys(CoreValue, 0.0), **(values or {})},
        tags=list(tags),
        sentiment=0.5,
        wall="tower" if medium is Medium.MURAL else None,
    )


def remembers(
    owner: str, work: Work, content: str, when: datetime, *, salience: float = 0.8
) -> Memory:
    """`owner`'s memory of `work`: about its artist, unless they're the artist."""
    return Memory(
        owner=owner,
        kind=MemoryKind.WORK,
        content=content,
        salience=salience,
        valence=0.5,
        timestamp=when,
        about=[] if owner == work.artist else [work.artist],
        topics=work.tags[:3],
        work_id=work.id,
    )
