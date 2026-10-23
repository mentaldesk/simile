from collections.abc import Iterator

import pytest

from simile.voice import FakeSynthesiser
from simile.voicing import eleven


@pytest.fixture
def synthesiser() -> Iterator[FakeSynthesiser]:
    fake = FakeSynthesiser()
    yield fake
    fake.open_gates()


@pytest.fixture(autouse=True)
def no_elevenlabs(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reads the real key or reaches ElevenLabs."""
    monkeypatch.delenv(eleven.ENV, raising=False)
    monkeypatch.setattr(eleven, "_keychain", lambda *flags, **options: None)
    monkeypatch.setattr(eleven, "API", "http://elevenlabs.invalid")
