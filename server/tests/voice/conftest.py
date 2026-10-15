from collections.abc import Iterator

import pytest

from simile.voice import FakeSynthesiser


@pytest.fixture
def synthesiser() -> Iterator[FakeSynthesiser]:
    fake = FakeSynthesiser()
    yield fake
    fake.open_gates()
