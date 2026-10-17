import sys
from collections.abc import Mapping

from simile.memory import MemoryStore
from simile.protocol import Artist, WorksMessage, WrittenWork
from simile.schema import PLAYER_ID, Id, Medium, Memory, MemoryKind, Npc, Work
from simile.sim import Clock
from simile.works.config import DEFAULT_CONFIG, WorksConfig
from simile.works.reading import name_of
from simile.works.store import WorksStore


class PlayerWorks:
    """The player at a news terminal's Village tab: `list_works` and `read_work` each get the
    `works` to send back, and reading a piece stores it as the player's own `work` memory. No
    LLM call."""

    def __init__(
        self,
        works: WorksStore,
        memory: MemoryStore,
        clock: Clock,
        npcs: Mapping[Id, Npc],
        *,
        config: WorksConfig = DEFAULT_CONFIG,
    ) -> None:
        self.works = works
        self.memory = memory
        self.clock = clock
        self.npcs = npcs
        self.config = config

    def listing(self) -> WorksMessage:
        read = self._read()
        return WorksMessage(
            works=[
                WrittenWork(
                    work_id=work.id,
                    title=work.title,
                    artist=Artist(id=work.artist, name=name_of(self.npcs, work.artist)),
                    form=work.form,
                    text=work.text,
                    statement=work.statement,
                    created=work.created,
                    read=work.id in read,
                )
                for work in self.works.latest(Medium.WRITING, self.config.listed)
            ]
        )

    def read(self, work_id: str) -> WorksMessage:
        work = self.works.get(work_id)
        if work is not None and work.medium is Medium.WRITING and work_id not in self._read():
            self.memory.add(self._remember(work))
        return self.listing()

    def _read(self) -> set[str]:
        memories = self.memory.recall(
            PLAYER_ID, self.clock.now, kind=MemoryKind.WORK, k=sys.maxsize
        )
        return {memory.work_id for memory in memories if memory.work_id}

    def _remember(self, work: Work) -> Memory:
        return Memory(
            owner=PLAYER_ID,
            kind=MemoryKind.WORK,
            content=f'I read {name_of(self.npcs, work.artist)}\'s "{work.title}" on the news '
            "terminal.",
            salience=self.config.player_salience,
            valence=0,
            timestamp=self.clock.now,
            about=[work.artist],
            topics=work.tags[: self.config.topics],
            work_id=work.id,
        )
