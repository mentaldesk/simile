from datetime import timedelta
from pathlib import Path

import pytest

from simile.gallery import GalleryStore

from .conftest import NOW

FRAMES = [("gallery", "painting_2"), ("gallery", "painting_1"), ("gallery", "painting_3")]


def test_new_paintings_fill_the_empty_frames_in_order(store: GalleryStore) -> None:
    first = store.hang("a", "<svg/>", b"A", FRAMES, NOW)
    second = store.hang("b", "<svg/>", b"B", FRAMES, NOW + timedelta(hours=1))

    assert [first, second] == FRAMES[:2]
    assert store.hanging() == {FRAMES[0]: "a", FRAMES[1]: "b"}


def test_once_every_frame_is_full_a_new_painting_replaces_the_one_hung_longest_ago(
    store: GalleryStore,
) -> None:
    for hour, work in enumerate("abc"):
        store.hang(work, "<svg/>", work.encode(), FRAMES, NOW + timedelta(hours=hour))

    replaced = [
        store.hang(work, "<svg/>", work.encode(), FRAMES, NOW + timedelta(hours=hour))
        for hour, work in enumerate("de", start=3)
    ]

    assert replaced == FRAMES[:2]
    assert store.hanging() == {FRAMES[0]: "d", FRAMES[1]: "e", FRAMES[2]: "c"}
    assert store.picture("a") == b"a"
    assert store.picture("d") == b"d"
    assert store.picture("z") is None


def test_hanging_needs_a_frame(store: GalleryStore) -> None:
    with pytest.raises(ValueError, match="no frames"):
        store.hang("a", "<svg/>", b"", [], NOW)


def test_keeps_what_hangs_across_a_restart(tmp_path: Path) -> None:
    with GalleryStore(tmp_path / "data" / "simile.db") as store:
        store.hang("a", "<svg/>", b"png", FRAMES, NOW)

    with GalleryStore(tmp_path / "data" / "simile.db") as store:
        assert store.hanging() == {FRAMES[0]: "a"}
        assert store.picture("a") == b"png"
