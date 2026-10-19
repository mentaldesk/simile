from datetime import timedelta

from simile.behaviour import MuralSpot, Places
from simile.gallery import Gallery, GalleryStore, frames_of, taking_turns
from simile.protocol import Artist, Frame, Painting, PaintingsMessage
from simile.schema import Medium, Npc, Tile
from simile.sim import Clock
from simile.works import WorksStore
from simile.world.map import with_every_location

from .conftest import KOFI, MAPS, NOW, RESIDENTS, painting

FRAMES = frames_of(MAPS)


def test_every_painting_on_the_gallery_map_is_a_frame_nearest_the_door_first() -> None:
    assert sorted(frame.id for frame in FRAMES) == sorted(f"painting_{n}" for n in range(1, 14))
    assert {frame.map for frame in FRAMES} == {"gallery"}
    [door] = [door.inside for door in MAPS["gallery"].doors]
    distances = [
        ((frame.stand[0].x - door.x) ** 2 + (frame.stand[0].y - door.y) ** 2) for frame in FRAMES
    ]
    assert distances == sorted(distances)
    assert FRAMES[0].id in {"painting_10", "painting_11"}


def test_the_message_has_every_frame_and_what_hangs_in_it(
    store: GalleryStore, works: WorksStore
) -> None:
    sent: list[PaintingsMessage] = []
    gallery = Gallery(FRAMES, store, works, Clock(NOW), RESIDENTS)
    gallery.hung = lambda: sent.append(gallery.message())
    works.add(painting("kofi-1"))

    hung = gallery.hang(painting("kofi-1"), "<svg/>", b"png")

    first = FRAMES[0]
    assert hung == ("gallery", first.id)
    [message] = sent
    assert message == gallery.message()
    assert len(message.frames) == 13
    assert message.frames[0] == Frame(
        id=first.id,
        map="gallery",
        painting=Painting(
            work_id="kofi-1",
            title="Painting kofi-1",
            artist=Artist(id="kofi", name=KOFI.name),
            statement="What kofi-1 says.",
            image="/api/gallery/kofi-1.png",
        ),
    )
    assert all(frame.painting is None for frame in message.frames[1:])
    assert gallery.showing() == {("gallery", first.id): works.get("kofi-1")}


def test_a_new_painting_replaces_the_one_hung_longest_ago(
    store: GalleryStore, works: WorksStore
) -> None:
    clock = Clock(NOW)
    gallery = Gallery(FRAMES[:2], store, works, clock, RESIDENTS)
    for n in range(3):
        works.add(painting(f"p{n}"))
        gallery.hang(painting(f"p{n}"), "<svg/>", b"")
        clock.now = clock.now.replace(hour=clock.now.hour + 1)

    showing = {frame: work.id for frame, work in gallery.showing().items()}
    assert showing == {("gallery", FRAMES[0].id): "p2", ("gallery", FRAMES[1].id): "p1"}


def test_a_painting_hung_earlier_is_the_first_replaced(
    store: GalleryStore, works: WorksStore
) -> None:
    gallery = Gallery(FRAMES[:2], store, works, Clock(NOW), RESIDENTS)
    for n, hours_ago in enumerate((1, 30)):
        works.add(painting(f"p{n}"))
        gallery.hang(painting(f"p{n}"), "<svg/>", b"", NOW - timedelta(hours=hours_ago))
    works.add(painting("p2"))

    gallery.hang(painting("p2"), "<svg/>", b"")

    showing = {frame: work.id for frame, work in gallery.showing().items()}
    assert showing == {("gallery", FRAMES[0].id): "p0", ("gallery", FRAMES[1].id): "p2"}


PLACES = Places(with_every_location(MAPS))
WALL = MuralSpot("tower", Tile(x=1, y=2))


def turns(works: WorksStore, wall: MuralSpot | None = WALL) -> MuralSpot | None:
    def pick(npc: Npc) -> MuralSpot | None:
        return wall

    return taking_turns(pick, works, PLACES)(KOFI)


def at_home(npc: Npc) -> MuralSpot:
    return MuralSpot(npc.home, PLACES.location(npc.home).entry)


def test_a_muralist_paints_for_the_gallery_at_home_after_two_murals_in_a_row(
    works: WorksStore,
) -> None:
    assert turns(works) == WALL
    works.add(painting("m1", medium=Medium.MURAL, wall="tower", hours_ago=3))
    assert turns(works) == WALL
    works.add(painting("m2", medium=Medium.MURAL, wall="tower", hours_ago=2))
    assert turns(works) == at_home(KOFI)
    works.add(painting("p1", hours_ago=1))
    assert turns(works) == WALL


def test_a_muralist_with_no_wall_worth_painting_paints_for_the_gallery(works: WorksStore) -> None:
    assert turns(works, wall=None) == at_home(KOFI)
    assert at_home(KOFI).wall == KOFI.home == "house_6"


def test_a_muralist_whose_home_is_off_the_village_keeps_to_walls(works: WorksStore) -> None:
    upstairs = KOFI.model_copy(update={"home": "coffee_shop"})
    works.add(painting("m1", medium=Medium.MURAL, wall="tower"))

    def pick(npc: Npc) -> MuralSpot | None:
        return WALL

    assert taking_turns(pick, works, PLACES)(upstairs) == WALL
