import importlib
from collections.abc import Callable, Mapping, Sequence

import pytest

from simile.sim import System, World

MakePackage = Callable[[dict[str, str]], str]
SystemFactory = Callable[[World], System]

SIM_LIFESPAN = "from simile.sim.lifespan import running\n"

MODULE_LIFESPAN = (
    "from contextlib import asynccontextmanager\n"
    "from simile.sim import world_of\n"
    "systems = []\n"
    "@asynccontextmanager\n"
    "async def lifespan(app):\n"
    "    world = world_of(app)\n"
    "    for make_system in systems:\n"
    "        world.loop.register(make_system(world))\n"
    "    yield\n"
)


@pytest.fixture
def make_village(make_package: MakePackage) -> Callable[..., str]:
    """A package with the sim lifespan, modules whose lifespans register the given systems, and
    any extra files."""

    def make(
        modules: Mapping[str, Sequence[SystemFactory]], files: Mapping[str, str] | None = None
    ) -> str:
        package = make_package(
            {
                "sim/lifespan.py": SIM_LIFESPAN,
                **{f"{module}/lifespan.py": MODULE_LIFESPAN for module in modules},
                **(files or {}),
            }
        )
        for module, systems in modules.items():
            importlib.import_module(f"{package}.{module}.lifespan").systems.extend(systems)
        return package

    return make
