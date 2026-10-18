import asyncio
import io
import logging
import re
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient
from typer.testing import CliRunner

from simile.app import create_app
from simile.cli import create_cli
from simile.gallery import Gallery, GalleryStore, frames_of
from simile.llm import FakeProvider, LLMClient
from simile.llm.provider import Request
from simile.memory import MemoryStore, memory_of
from simile.npc import NPCS_DIR, load_npcs
from simile.schema import Medium, MemoryKind
from simile.sim import Clock
from simile.works import DEFAULT_CONFIG, Maker, WorksStore, works_of
from simile.works.render import canvas, painting_canvas
from simile.works.starters import PLAN, Slot, Starter, commission, load, missing, seed
from simile.works.svg import checked
from simile.world.map import load_map, load_maps

from .conftest import mural, mural_reply, reply, svg

MakePackage = Callable[[dict[str, str]], str]

NOW = datetime(2026, 3, 14, 12, tzinfo=UTC)
RESIDENTS = {npc.id: npc for npc in load_npcs(NPCS_DIR)}
WALLS = {wall.id: wall for wall in load_map().murals}
STARTERS = load()
runner = CliRunner()


def answer(request: Request) -> str:
    asked = request.messages[-1].content
    if size := re.search(r'viewBox="0 0 (\d+) (\d+)"', asked):
        return mural_reply(svg=svg(int(size[1]), int(size[2])))
    return reply()


def test_today_has_a_mural_on_four_walls_six_pieces_and_five_paintings() -> None:
    works = [starter.work for starter in STARTERS]

    assert Counter(work.medium for work in works) == {
        Medium.MURAL: 4,
        Medium.WRITING: 6,
        Medium.PAINTING: 5,
    }
    assert len({work.wall for work in works if work.wall}) == 4
    assert missing(PLAN, works) == []
    assert works == sorted(works, key=lambda work: work.created)


@pytest.mark.parametrize("starter", STARTERS, ids=lambda starter: starter.work.id)
def test_each_starter_is_by_a_resident_in_their_craft_with_a_picture_that_fits(
    starter: Starter,
) -> None:
    work = starter.work
    craft = RESIDENTS[work.artist].craft
    assert craft is not None and work.form == craft.form
    assert work.medium is craft.medium or (craft.medium, work.medium) == (
        Medium.MURAL,
        Medium.PAINTING,
    )
    if work.medium is Medium.WRITING:
        assert starter.svg is None and starter.png is None
        return
    assert starter.svg is not None and starter.png is not None
    size = canvas(WALLS[work.wall]) if work.wall else painting_canvas()
    config = DEFAULT_CONFIG
    checked(
        starter.svg,
        *size,
        chars=config.svg_chars,
        elements=config.svg_elements,
        tolerance=config.aspect_tolerance,
    )
    assert Image.open(io.BytesIO(starter.png)).size == size


def gallery(works: WorksStore, store: GalleryStore) -> Gallery:
    return Gallery(frames_of(load_maps()), store, works, Clock(NOW), RESIDENTS)


def test_a_fresh_save_starts_with_the_murals_up_the_writing_out_and_the_paintings_hung() -> None:
    with (
        WorksStore(":memory:") as works,
        MemoryStore(":memory:") as memory,
        GalleryStore(":memory:") as store,
    ):
        hall = gallery(works, store)
        seeded = seed(works, memory, RESIDENTS, NOW, hang=hall.hang)

        assert len(seeded) == len(STARTERS)
        showing = works.showing()
        murals = [w for w in seeded if w.medium is Medium.MURAL]
        assert {wall: w.id for wall, w in showing.items()} == {w.wall: w.id for w in murals}
        assert all(works.picture(w.id) for w in murals)
        assert len(works.latest(Medium.WRITING, 20)) == 6
        hung = hall.showing()
        paintings = [w for w in seeded if w.medium is Medium.PAINTING]
        assert sorted(w.id for w in hung.values()) == sorted(w.id for w in paintings)
        assert all(store.picture(w.id) for w in paintings)

    newest = max(work.created for work in seeded)
    assert newest == NOW - DEFAULT_CONFIG.starters_newest
    gaps = [b.created - a.created for a, b in zip(seeded, seeded[1:], strict=False)]
    made = [s.work.created for s in STARTERS]
    assert gaps == [b - a for a, b in zip(made, made[1:], strict=False)]


def test_each_artist_remembers_making_theirs() -> None:
    with WorksStore(":memory:") as works, MemoryStore(":memory:") as memory:
        seeded = seed(works, memory, RESIDENTS, NOW)

        for artist in {work.artist for work in seeded}:
            remembered = memory.recall(artist, NOW, kind=MemoryKind.WORK, k=10)
            theirs = {work.id for work in seeded if work.artist == artist}
            assert {m.work_id for m in remembered} == theirs
            assert all(not m.about for m in remembered)


def test_nothing_is_seeded_twice_or_over_works_already_there() -> None:
    with WorksStore(":memory:") as works, MemoryStore(":memory:") as memory:
        assert seed(works, memory, RESIDENTS, NOW)
        assert seed(works, memory, RESIDENTS, NOW + timedelta(days=1)) == []
        assert len(works.by("kofi")) == 2

    with WorksStore(":memory:") as works, MemoryStore(":memory:") as memory:
        works.add(mural("m1", artist="kofi"))
        assert seed(works, memory, RESIDENTS, NOW) == []
        assert [work.id for work in works.by("kofi")] == ["m1"]


def maker(works: WorksStore, memory: MemoryStore, llm: LLMClient, hung: list[str]) -> Maker:
    def hang(work: object, svg: str, png: bytes) -> None:
        hung.append(work.id)  # type: ignore[attr-defined]

    return Maker(
        works,
        memory,
        Clock(NOW),
        lambda: llm,
        walls=list(WALLS.values()),
        npcs=RESIDENTS,
        hang=hang,
    )


def test_a_new_world_starts_one_work_each_for_its_most_creative_crafters_within_the_cap() -> None:
    cast = [RESIDENTS[id] for id in ("mirela", "kofi", "lachlan", "desmond", "ingrid", "priya")]
    llm = LLMClient(FakeProvider([answer] * 20))
    config = DEFAULT_CONFIG.model_copy(update={"starters": 4})
    hung: list[str] = []

    async def run() -> list[tuple[str, str, str | None]]:
        with WorksStore(":memory:") as works, MemoryStore(":memory:") as memory:
            walls = [WALLS["tower"]]
            busy = maker(works, memory, llm, hung)
            tasks = commission(busy, works, cast, walls, NOW, config)
            made = [work for work in await asyncio.gather(*tasks) if work is not None]
            assert commission(busy, works, cast, walls, NOW, config) == []
            return [(work.artist, work.medium.value, work.wall) for work in made]

    made = asyncio.run(run())

    assert sorted(made) == [
        ("desmond", "writing", None),
        ("ingrid", "painting", None),
        ("kofi", "mural", "tower"),
        ("lachlan", "writing", None),
    ]
    assert len(hung) == 1


def lifespans(make_package: MakePackage, *modules: str) -> str:
    return make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import *  # noqa: F403\n"
            for module in modules
        }
    )


def test_the_server_seeds_a_fresh_save_of_today_once(
    make_package: MakePackage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "simile.db"))
    package = lifespans(make_package, "gallery", "memory", "works")

    app = create_app(package)
    with TestClient(app):
        works, hall = works_of(app), app.state.gallery
        assert len(works.showing()) == 4
        assert len(works.latest(Medium.WRITING, 20)) == 6
        assert len(hall.showing()) == 5
        made = memory_of(app).recall("kofi", app.state.world.clock.now, kind=MemoryKind.WORK)
        assert len(made) == 2
        before = {work.id for artist in RESIDENTS for work in works.by(artist)}

    app = create_app(package)
    with TestClient(app):
        works = works_of(app)
        assert {work.id for artist in RESIDENTS for work in works.by(artist)} == before


def test_an_in_memory_store_is_never_seeded(make_package: MakePackage) -> None:
    app = create_app(lifespans(make_package, "gallery", "memory", "works"))

    with TestClient(app):
        assert works_of(app).empty()


def test_a_new_world_makes_its_starter_works_once(
    make_package: MakePackage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "simile.db"))
    monkeypatch.setattr("simile.casting.load_cast", lambda: object())
    package = lifespans(make_package, "gallery", "llm", "memory", "works")
    caplog.set_level(logging.INFO, "simile.works.lifespan")

    for _ in range(2):
        with TestClient(create_app(package)):
            pass

    assert caplog.text.count("Making 8 starter works for the new world") == 1


def test_the_command_makes_whats_missing_and_stops_at_the_first_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = (Slot("desmond", Medium.WRITING), Slot("priya", Medium.PAINTING))
    monkeypatch.setattr("simile.works.starters.PLAN", plan)
    out = tmp_path / "works"

    first = runner.invoke(create_cli(), ["works", "starter", "--out", str(out)])
    again = runner.invoke(create_cli(), ["works", "starter", "--out", str(out)])

    assert first.exit_code == 0, first.output
    assert "2 starter works. 2 LLM calls this run (1 work, 1 painting), 0 failed." in first.output
    assert [s.work.artist for s in load(out)] == ["desmond", "priya"]
    assert again.exit_code == 0
    assert "2 starter works. 0 LLM calls this run (none), 0 failed." in again.output

    def broken(request: Request) -> str:
        raise RuntimeError("no Claude today")

    monkeypatch.setattr("simile.works.starters.PLAN", (*plan, Slot("lachlan", Medium.WRITING)))
    monkeypatch.setattr("simile.works.cli.stand_in", broken)
    stopped = runner.invoke(create_cli(), ["works", "starter", "--out", str(out)])

    assert stopped.exit_code == 1
    assert "1 failed" in stopped.output
    assert "Stopped: lachlan couldn't make their writing." in stopped.output
    assert len(load(out)) == 2
