import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from simile.dolls.sprites import (
    HEIGHT_M,
    PPM,
    atlas,
    climber,
    enclosed,
    feet,
    frames,
    head,
    manifest,
    pack,
    seat,
)


def person(lean: float = 0.0, arms_up: bool = False, scale: float = 1.0) -> Image.Image:
    """A big head over a body whose legs reach `lean` of the height ahead of the head."""
    s = scale
    image = Image.new("RGBA", (round(400 * s), round(600 * s)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    top = 120 * s
    draw.ellipse((120 * s, top, 280 * s, top + 160 * s), (230, 170, 120, 255))
    draw.rectangle((150 * s, top + 160 * s, 250 * s, top + 300 * s), (40, 90, 200, 255))
    x = 200 * s + lean * 440 * s
    draw.polygon(
        [
            (160 * s, top + 300 * s),
            (240 * s, top + 300 * s),
            (x + 20 * s, top + 440 * s),
            (x - 60 * s, top + 440 * s),
        ],
        (60, 60, 90, 255),
    )
    if arms_up:
        draw.rectangle((90 * s, top - 100 * s, 110 * s, top + 40 * s), (230, 170, 120, 255))
        draw.rectangle((290 * s, top - 100 * s, 310 * s, top + 40 * s), (230, 170, 120, 255))
    return image


def test_stands_under_the_middle_of_its_head_on_its_lowest_row() -> None:
    x, y = feet(person(lean=0.15))

    assert x == pytest.approx(200, abs=1)
    assert y == 120 + 440 + 1


def test_a_climber_stands_under_the_middle_of_its_body_and_its_head_tops_it() -> None:
    middle, top = climber(person(arms_up=True))

    assert middle == pytest.approx(200, abs=2)
    assert top == 120


def test_a_climber_painted_bigger_is_scaled_to_stand_as_tall() -> None:
    made = frames(
        {"stand": person(), "climb": person(arms_up=True, scale=1.15)}, hands_up=["climb"]
    )

    def head_to_feet(image: Image.Image) -> int:
        return np.flatnonzero(np.asarray(image.getchannel("A")).any(axis=1))[-1] - climber(image)[1]

    assert head_to_feet(made["climb"].image) == pytest.approx(
        head_to_feet(made["stand"].image), abs=2
    )
    assert made["climb"].feet[0] == pytest.approx(climber(made["climb"].image)[0])


def test_frames_are_scaled_to_the_street_and_keep_the_head_one_size() -> None:
    made = frames({"stand": person(), "stride": person(lean=0.15), "big": person(scale=1.2)})

    stand = np.asarray(made["stand"].image.getchannel("A")) >= 128
    rows = np.flatnonzero(stand.any(axis=1))
    assert rows[-1] - rows[0] + 1 == pytest.approx(HEIGHT_M * PPM, abs=1.5)
    widths = {name: head(frame.image, 0.25 * HEIGHT_M * PPM)[1] for name, frame in made.items()}
    assert widths["big"] == pytest.approx(widths["stand"], abs=2)
    for frame in made.values():
        a = np.asarray(frame.image.getchannel("A")) >= 128
        assert frame.feet[1] == np.flatnonzero(a.any(axis=1))[-1] + 1
        assert frame.feet[0] == pytest.approx(head(frame.image, 0.25 * HEIGHT_M * PPM)[0])


def test_packs_every_frame_apart_into_one_atlas() -> None:
    images = {
        f"f{i}": Image.new("RGBA", (90 + 7 * i, 160 - 9 * i), (9, 9, 9, 255)) for i in range(12)
    }

    (width, height), places = pack(images)

    boxes = [(x, y, x + w, y + h) for x, y, w, h in places.values()]
    for i, a in enumerate(boxes):
        assert a[2] <= width and a[3] <= height
        for b in boxes[i + 1 :]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_the_manifest_has_each_frame_its_feet_and_each_pose() -> None:
    made = frames({"stand": person(), "stride": person(lean=0.15)})
    data, places = atlas(made)

    found = manifest(
        made, places, {"stand": ["stand"], "walk": ["stride", "stand"]}, "a.webp", id="a"
    )

    assert found["painted"] == "a.webp" and found["ppm"] == PPM
    assert found["poses"]["walk"] == ["stride", "stand"]
    sheet = Image.open(io.BytesIO(data))
    assert sheet.format == "WEBP"
    for name, entry in found["frames"].items():
        x, y, w, h = entry["frame"]
        assert x + w <= sheet.width and y + h <= sheet.height
        assert entry["feet"] == [round(made[name].feet[0], 1), round(made[name].feet[1], 1)]


def test_a_frame_in_the_air_is_lifted_so_its_head_is_as_high_as_the_other() -> None:
    crouched = person().transform(person().size, Image.Transform.AFFINE, (1, 0, 0, 0, 1, -60))

    made = frames({"stand": person(), "run": crouched, "land": person()}, lifted={"run": "land"})

    def top(name: str) -> float:
        frame = made[name]
        rows = np.flatnonzero(np.asarray(frame.image.getchannel("A")).any(axis=1))
        return frame.feet[1] - rows[0]

    assert top("run") == pytest.approx(top("land"), abs=1)
    assert made["run"].feet[1] > made["run"].image.height


def sitter(shins: int) -> Image.Image:
    """Facing right, its head's middle at 150 and the bottom of its thighs on row 210, its shins
    hanging from `shins`."""
    sitting = Image.new("RGBA", (300, 320), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sitting)
    draw.ellipse((100, 0, 200, 100), (230, 170, 120, 255))
    draw.rectangle((60, 100, 140, 200), (40, 90, 200, 255))
    draw.rectangle((60, 180, shins + 30, 210), (60, 60, 90, 255))
    draw.rectangle((shins, 180, shins + 30, 300), (60, 60, 90, 255))
    return sitting


@pytest.mark.parametrize("shins", [130, 230])
def test_a_seated_figure_sits_on_its_thighs_with_its_shins_under_its_head_or_ahead(
    shins: int,
) -> None:
    assert seat(sitter(shins), 150) == (150, 211)


def test_a_seated_frame_sits_under_the_middle_of_its_head_above_its_feet() -> None:
    made = frames({"stand": person(), "sit": sitter(130)}, seated=["sit"])

    x, y = made["sit"].seat
    assert x == pytest.approx(made["sit"].feet[0])
    assert y < made["sit"].feet[1] - 20


def test_only_clear_patches_the_outline_shuts_in_are_enclosed() -> None:
    pytest.importorskip("cv2")
    clear = np.ones((60, 60), dtype=bool)
    clear[10:50, 10:50] = False
    clear[20:30, 20:30] = True
    clear[35:60, 40:45] = True

    inside = enclosed(clear)

    assert inside[25, 25] and not inside[0, 0] and not inside[45, 42]
