import sqlite3
from collections.abc import Callable

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.memory import memory_of
from simile.sim import world_of
from simile.works import Maker, works_of

from .conftest import work

MakePackage = Callable[[dict[str, str]], str]


def test_the_server_keeps_a_maker_on_its_works_and_closes_them(make_package: MakePackage) -> None:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("llm", "memory", "works")
        }
    )
    app = create_app(package)

    with TestClient(app):
        maker = app.state.maker
        assert isinstance(maker, Maker)
        assert maker.works is works_of(app)
        assert maker.memory is memory_of(app)
        assert maker.clock is world_of(app).clock
        assert maker.llm() is app.state.llm
        store = works_of(app)
        store.add(work("a"))

    with pytest.raises(sqlite3.ProgrammingError):
        store.get("a")
