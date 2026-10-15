from collections.abc import Iterator

import pytest

from simile.memory import MemoryStore


@pytest.fixture
def store() -> Iterator[MemoryStore]:
    with MemoryStore(":memory:") as store:
        yield store
