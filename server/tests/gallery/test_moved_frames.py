from simile.gallery import GalleryStore
from simile.gallery.gallery import Gallery, frames_of, key
from simile.sim import Clock
from simile.works import WorksStore

from .conftest import MAPS, NOW, RESIDENTS, painting


def test_paintings_hung_on_todays_gallery_map_stay_in_their_frames(
    store: GalleryStore, works: WorksStore
) -> None:
    frames = frames_of(MAPS)
    [eleventh] = [frame for frame in frames if frame.id == "painting_11"]
    for work in (painting("kofi-1"), painting("tobias-1", "tobias")):
        works.add(work)
    store.hang("kofi-1", "<svg/>", b"png", [("gallery", "painting_11")], NOW)
    store.hang("tobias-1", "<svg/>", b"png", [("gallery", "painting_1")], NOW)

    gallery = Gallery(frames, store, works, Clock(NOW), RESIDENTS)

    [first] = [frame for frame in frames if frame.id == "painting_1"]
    assert store.hanging() == {key(eleventh): "kofi-1", key(first): "tobias-1"}
    shown = {frame.id: frame.painting for frame in gallery.message().frames if frame.painting}
    assert {frame: painted.work_id for frame, painted in shown.items()} == {
        "painting_11": "kofi-1",
        "painting_1": "tobias-1",
    }
    assert eleventh.map == "gallery_floor_2"
