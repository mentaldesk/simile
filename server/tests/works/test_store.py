from pathlib import Path

from starlette.applications import Starlette

from simile.memory import MemoryStore
from simile.schema import Medium
from simile.works import WorksStore, works_of

from .conftest import FIXTURE_WORKS, work


def test_stores_and_gets_a_work(works: WorksStore) -> None:
    for fixture in FIXTURE_WORKS:
        works.add(fixture)

    assert [works.get(fixture.id) for fixture in FIXTURE_WORKS] == FIXTURE_WORKS
    assert works.get("nothing") is None


def test_adding_a_work_again_replaces_it(works: WorksStore) -> None:
    works.add(work("a"))
    works.add(work("a", title="Revised"))

    assert works.by("viktor") == [work("a", title="Revised")]


def test_lists_the_latest_in_a_medium_newest_first(works: WorksStore) -> None:
    works.add(work("old", hours_ago=5))
    works.add(work("new", hours_ago=1))
    works.add(work("middle", artist="mei", hours_ago=3))
    works.add(work("mural", artist="suki", medium=Medium.MURAL))

    assert [w.id for w in works.latest(Medium.WRITING)] == ["new", "middle", "old"]
    assert [w.id for w in works.latest(Medium.WRITING, 2)] == ["new", "middle"]
    assert [w.id for w in works.latest(Medium.MURAL)] == ["mural"]


def test_lists_an_artists_works_newest_first(works: WorksStore) -> None:
    works.add(work("old", hours_ago=5))
    works.add(work("new", hours_ago=1))
    works.add(work("theirs", artist="mei"))

    assert [w.id for w in works.by("viktor")] == ["new", "old"]
    assert [w.id for w in works.by("viktor", 1)] == ["new"]
    assert works.by("suki") == []


def test_the_server_keeps_works_in_the_memory_database(tmp_path: Path) -> None:
    app = Starlette()
    app.state.memory = MemoryStore(tmp_path / "simile.db")

    with works_of(app) as store:
        assert works_of(app) is store
        store.add(work("a"))
    app.state.memory.close()

    with WorksStore(tmp_path / "simile.db") as reopened:
        assert reopened.get("a") == work("a")
