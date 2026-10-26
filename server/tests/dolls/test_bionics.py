import numpy as np
import pytest
from PIL import Image, ImageDraw

from simile.characters.palette import PLAYER
from simile.dolls.bionics import (
    COMBINATIONS,
    FITTED,
    LAYERS,
    changed,
    edit_prompt,
    figure_id,
    hides,
    laid,
    layers,
    missing,
    patches,
    shows,
    spared,
)
from simile.dolls.figure import FRAMES, stand_prompt
from simile.dolls.flux import FakePainter, figure, fitted, named_colours
from simile.dolls.measure import face_marks
from simile.schema.player import Bionic, Body

from .keyed import keyed

BIONIC_LEGS, FEET, DATAJACK, EYE = FITTED
SIZE = (300, 400)


def whole() -> Image.Image:
    return figure(SIZE, named_colours(stand_prompt(PLAYER, "player")))


def with_parts(*parts: Bionic) -> Image.Image:
    painting = whole()
    for part in parts:
        painting = fitted(painting, edit_prompt("stand", part, PLAYER))
    return keyed(painting)


def test_every_combination_once_fewest_first() -> None:
    lower = [(), (BIONIC_LEGS,), (FEET,), (BIONIC_LEGS, FEET)]
    upper = [(), (DATAJACK,), (EYE,), (DATAJACK, EYE)]
    every = {low + up for low in lower for up in upper} - {()}

    assert len(COMBINATIONS) == len(every) == 15 and set(COMBINATIONS) == every
    assert [len(c) for c in COMBINATIONS] == sorted(len(c) for c in COMBINATIONS)
    assert all(list(c) == sorted(c, key=FITTED.index) for c in COMBINATIONS)


def test_the_lower_body_is_one_layer_and_each_other_part_its_own() -> None:
    assert layers((BIONIC_LEGS, FEET, DATAJACK, EYE)) == [(BIONIC_LEGS, FEET), (DATAJACK,), (EYE,)]
    assert layers((BIONIC_LEGS, EYE)) == [(BIONIC_LEGS,), (EYE,)]
    assert layers((DATAJACK,)) == [(DATAJACK,)]


def test_each_layer_is_painted_after_the_one_it_adds_to() -> None:
    assert set(LAYERS) == {
        (BIONIC_LEGS,),
        (FEET,),
        (BIONIC_LEGS, FEET),
        (DATAJACK,),
        (EYE,),
    }
    assert all(layer[:-1] in LAYERS[:n] for n, layer in enumerate(LAYERS) if len(layer) > 1)


@pytest.mark.parametrize(
    ("fitted_", "id_"),
    [
        ((), "player"),
        ((BIONIC_LEGS,), "player_bionic_legs"),
        ((EYE, FEET), "player_feet_eye"),
        ((EYE, DATAJACK, BIONIC_LEGS), "player_bionic_legs_datajack_eye"),
    ],
)
def test_names_the_figure_for_whatever_is_fitted(fitted_: tuple, id_: str) -> None:
    assert figure_id(fitted_) == id_


def test_every_grade_of_a_line_is_one_figure_and_the_power_cell_none() -> None:
    first = Body(legs=BIONIC_LEGS, feet=FEET, stomach=Bionic.POWER_CELL)
    best = Body(legs=Bionic.BIONIC_LEGS_3, feet=Bionic.SPRING_FEET_2, stomach=Bionic.POWER_CELL_3)

    assert figure_id(first.bionics) == figure_id(best.bionics) == "player_bionic_legs_feet"
    assert figure_id(Body(stomach=Bionic.POWER_CELL).bionics) == "player"


def test_a_body_names_its_figure_by_its_bionics_whichever_eye() -> None:
    left = Body(left_eye=EYE, vertebra=DATAJACK)
    right = Body(right_eye=EYE, vertebra=DATAJACK, left_kidney="sold")

    assert figure_id(left.bionics) == figure_id(right.bionics) == "player_datajack_eye"


def test_the_eye_isnt_seen_from_behind() -> None:
    assert [f for f in FRAMES if not shows(EYE, f)] == ["climb"]
    assert all(shows(BIONIC_LEGS, f) and shows(DATAJACK, f) for f in FRAMES)


def test_each_part_is_asked_for_alone_over_the_whole_player() -> None:
    legs, eye = edit_prompt("run", BIONIC_LEGS, PLAYER), edit_prompt("run", EYE, PLAYER)

    assert "now with both legs replaced" in legs and "eye nearer the ear" not in legs
    assert " shorts and " in legs and " trousers and " not in legs
    assert "now with the eye nearer the ear" in eye and " trousers and " in eye
    assert "one bright red bionic eye" in eye and "simple dot eyes" in legs


def test_the_feet_are_asked_for_in_place_of_the_sneakers() -> None:
    feet = edit_prompt("stand", FEET, PLAYER)
    over_legs = edit_prompt("stand", FEET, PLAYER, (BIONIC_LEGS,))

    assert "spring feet" in feet and "pure white sneakers" not in feet
    assert " trousers" in feet and " shorts" in over_legs and " trousers" not in over_legs
    assert hides((BIONIC_LEGS, FEET)) == {"shoe"} and hides((BIONIC_LEGS,)) == set()


def test_climbing_asks_for_no_face() -> None:
    climb = edit_prompt("climb", DATAJACK, PLAYER)

    assert "datajack" in climb and "eye" not in climb


def test_finds_each_part_painted() -> None:
    assert missing(with_parts(), FITTED, "stand") == [
        "bionic_legs",
        "feet",
        "datajack",
        "eye",
    ]
    assert (
        missing(with_parts(BIONIC_LEGS, DATAJACK, EYE), (BIONIC_LEGS, DATAJACK, EYE), "stand") == []
    )
    assert missing(with_parts(BIONIC_LEGS, FEET), (BIONIC_LEGS, FEET), "stand") == []
    assert missing(with_parts(BIONIC_LEGS), (BIONIC_LEGS, FEET), "stand") == ["feet"]
    assert missing(with_parts(DATAJACK), (BIONIC_LEGS, DATAJACK, EYE), "climb") == ["bionic_legs"]


def test_both_eyes_painted_red_is_one_too_many() -> None:
    painting = with_parts(EYE)
    w, h = SIZE
    ImageDraw.Draw(painting).ellipse((0.47 * w, 0.21 * h, 0.5 * w, 0.24 * h), (222, 30, 30))

    assert missing(painting, (EYE,), "stand") == ["two eyes"]


def test_an_eye_wider_than_the_walks_is_too_big() -> None:
    painting = with_parts(EYE)
    w, h = SIZE
    ImageDraw.Draw(painting).ellipse((0.5 * w, 0.15 * h, 0.62 * w, 0.24 * h), (222, 30, 30))

    assert missing(with_parts(EYE), (EYE,), "stand") == []
    assert missing(painting, (EYE,), "stand") == ["eye too big"]


def test_the_face_check_spares_the_eye_and_nothing_else() -> None:
    eyed = with_parts(EYE)
    w, h = SIZE
    marked = eyed.copy()
    ImageDraw.Draw(marked).ellipse((0.53 * w, 0.27 * h, 0.6 * w, 0.32 * h), (139, 155, 180))

    assert face_marks(eyed, PLAYER, spared(eyed)) == 0
    assert face_marks(marked, PLAYER, spared(marked)) > 0


def test_counts_patches_biggest_first() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[1:3, 1:3] = True
    mask[5:9, 5:9] = True

    assert [int(p.sum()) for p in patches(mask)] == [16, 4]


def test_a_part_is_where_painting_it_changed_the_frame_near_it() -> None:
    player = with_parts()
    eye = with_parts(EYE)
    w, h = SIZE
    ImageDraw.Draw(eye).rectangle((0.45 * w, 0.8 * h, 0.55 * w, 0.85 * h), (139, 155, 180))

    where = changed(player, eye, (EYE,))

    lens = np.argwhere(np.asarray(eye.convert("RGB")) == (222, 30, 30))
    assert where[lens[:, 0], lens[:, 1]].all()
    assert not where[int(0.82 * h), int(0.5 * w)]
    assert where.sum() < 0.05 * where.size


def test_parts_are_laid_over_the_player_and_nothing_else_changes() -> None:
    player = with_parts()
    legs, eye = with_parts(BIONIC_LEGS), with_parts(EYE)
    w, h = SIZE

    both = laid(
        player, [(legs, changed(player, legs, (BIONIC_LEGS,))), (eye, changed(player, eye, (EYE,)))]
    )

    assert missing(both, (BIONIC_LEGS, EYE), "stand") == []
    before, after = np.asarray(player), np.asarray(both)
    assert (before[: int(0.12 * h)] == after[: int(0.12 * h)]).all()
    assert (before[:, : int(0.2 * w)] == after[:, : int(0.2 * w)]).all()


def test_the_lower_body_is_laid_as_one_with_the_legs_and_the_feet() -> None:
    player, both = with_parts(), with_parts(BIONIC_LEGS, FEET)
    h = SIZE[1]

    laid_over = laid(player, [(both, changed(player, both, (BIONIC_LEGS, FEET)))])

    assert missing(laid_over, (BIONIC_LEGS, FEET), "stand") == []
    assert (np.asarray(player)[: h // 2] == np.asarray(laid_over)[: h // 2]).all()


def test_the_fake_painter_paints_what_an_edit_asks_for() -> None:
    painter = FakePainter()
    base = painter.paint(stand_prompt(PLAYER, "player"), SIZE, 1)

    edited = painter.paint(edit_prompt("stand", EYE, PLAYER), SIZE, 1, [base])

    assert missing(keyed(edited), FITTED, "stand") == ["bionic_legs", "feet", "datajack"]
