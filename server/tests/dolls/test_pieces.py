import numpy as np
import pytest
from PIL import ImageDraw

from simile.characters.palette import PLAYER
from simile.dolls.colour import muted, rgb
from simile.dolls.look import Look
from simile.dolls.pieces import Piece, flat_pieces
from simile.dolls.shapes import FACE_R, PIECES, STANDING_HEIGHT, strand
from simile.schema import Accessory, Appearance, Build, HairStyle

HEAD = ("glasses", "sunglasses", "cap", "beanie", "headphones")
BODY = ("scarf", "backpack", "apron")


def appearance(**changes: object) -> Appearance:
    return PLAYER.model_copy(update=changes)


def colours(image) -> set[tuple[int, int, int]]:
    a = np.asarray(image.convert("RGBA"))
    solid = a[a[..., 3] == 255][:, :3]
    found, counts = np.unique(solid, axis=0, return_counts=True)
    return {tuple(int(v) for v in c) for c, n in zip(found, counts, strict=True) if n > 20}


@pytest.mark.parametrize("style", list(HairStyle))
@pytest.mark.parametrize("build", list(Build))
def test_every_piece_draws_for_every_hair_style_and_build(style: HairStyle, build: Build) -> None:
    look = Look.of(appearance(hair_style=style, build=build), "someone")

    pieces = flat_pieces(look, 2.0)

    assert set(pieces) == set(PIECES)
    for name, piece in pieces.items():
        w, h = piece.image.size
        assert piece.image.getchannel("A").getbbox() is not None, name
        assert -w < piece.pivot[0] < 2 * w and -h < piece.pivot[1] < 2 * h, name
    assert set(pieces["torso"].joints) == {"neck", "shoulder", "hip"}
    for view in ("front", "back"):
        assert set(pieces[f"torso_{view}"].joints) == {
            "neck",
            "shoulder_left",
            "shoulder_right",
            "hip_left",
            "hip_right",
        }
    assert set(pieces["upper_leg"].joints) == {"knee"}
    assert set(pieces["lower_leg"].joints) == {"ankle"}


@pytest.mark.parametrize("accessory", [*HEAD, *BODY])
def test_every_accessory_shows_in_every_view(accessory: str) -> None:
    look = Look.of(appearance(accessories=[Accessory(accessory)]), "someone")
    bare = Look.of(appearance(accessories=[]), "someone")
    pieces = ("head", "head_front", "head_back") if accessory in HEAD else ("torso",)
    pieces += ("torso_front", "torso_back") if accessory in BODY else ()

    worn, plain = flat_pieces(look, 2.0, pieces), flat_pieces(bare, 2.0, pieces)

    for name in pieces:
        assert worn[name].image.tobytes() != plain[name].image.tobytes(), name


def test_skin_is_kept_and_everything_else_muted() -> None:
    a = appearance(top_colour="#2ce8f5", skin="#733e39")

    look = Look.of(a, "someone")

    assert look.skin == rgb("#733e39")
    assert look.top == muted(rgb("#2ce8f5")) != rgb("#2ce8f5")


def test_the_pieces_are_cut_from_the_looks_colours() -> None:
    look = Look.of(PLAYER, "player")

    pieces = flat_pieces(look, 4.0)

    assert {look.skin, look.hair} <= colours(pieces["head"].image)
    assert {look.skin, look.hair} <= colours(pieces["head_front"].image)
    assert look.hair in colours(pieces["head_back"].image)
    for torso in ("torso", "torso_front", "torso_back"):
        assert {look.top, look.bottom} <= colours(pieces[torso].image), torso
    assert look.accent in colours(pieces["torso_back"].image)
    assert look.top in colours(pieces["upper_arm"].image)
    assert look.skin in colours(pieces["lower_arm"].image)
    assert look.bottom in colours(pieces["upper_leg"].image)
    assert look.shoe in colours(pieces["shoe"].image)
    assert look.shoe in colours(pieces["shoe_front"].image)


def test_dolls_are_about_four_heads_tall() -> None:
    assert 4.0 <= STANDING_HEIGHT / (2 * FACE_R[1]) <= 4.5


SCALE = 6.0


def at(piece: Piece, x: float, y: float) -> tuple[int, ...]:
    """The drawn colour at (x, y) units from the piece's pivot."""
    px = round(piece.pivot[0] + x * SCALE), round(piece.pivot[1] + y * SCALE)
    return piece.drawn.getpixel(px)


@pytest.mark.parametrize("view", ["torso_front", "torso_back"])
def test_nothing_shows_between_the_legs(view: str) -> None:
    look = Look.of(appearance(accessories=[]), "someone")

    torso = flat_pieces(look, SCALE, (view,))[view]

    assert at(torso, 0.0, 4.4)[3] == 0
    assert at(torso, 0.0, -2.0)[:3] == look.bottom


@pytest.mark.parametrize("hat", ["cap", "beanie"])
def test_hair_shows_under_a_hat_from_the_side(hat: str) -> None:
    look = Look.of(appearance(accessories=[Accessory(hat)]), "someone")

    head = flat_pieces(look, SCALE, ("head",))["head"]

    assert at(head, -8.0, -8.0)[:3] == look.hair


@pytest.mark.parametrize("style", ["buzz", "short", "bob", "long", "ponytail", "bun"])
def test_front_strands_stay_in_the_hair(style: str) -> None:
    look = Look.of(appearance(hair_style=HairStyle(style), accessories=[]), "someone")
    head = flat_pieces(look, SCALE, ("head_front",))["head_front"]
    drawn = np.asarray(head.drawn)

    ys, xs = np.nonzero((drawn[..., :3] == strand(look)).all(axis=2))

    assert len(ys) > 0
    for y, x in zip(ys, xs, strict=True):
        around = drawn[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2, :3]
        assert not (around == look.skin).all(axis=2).any(), (x, y)


@pytest.mark.parametrize("style", list(HairStyle))
@pytest.mark.parametrize("hat", [None, "cap", "beanie"])
def test_no_head_has_a_hole_in_it(style: HairStyle, hat: str | None) -> None:
    look = Look.of(
        appearance(hair_style=style, accessories=[Accessory(hat)] if hat else []), "someone"
    )

    for name, head in flat_pieces(look, 12.0, ("head", "head_front", "head_back")).items():
        solid = head.image.getchannel("A").point(lambda a: 255 if a >= 240 else 0)
        ImageDraw.floodfill(solid, (0, 0), 128)
        assert (np.asarray(solid) == 0).sum() == 0, name
