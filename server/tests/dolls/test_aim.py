import json
import shutil
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from simile.dolls import aim
from simile.dolls.bionics import COMBINATIONS, figure_id, missing
from simile.dolls.build import CONTENT, GROUND, SIZE, Cached
from simile.schema import PLAYER_ID

from .keyed import keyed

SOME = (COMBINATIONS[0], COMBINATIONS[-1])
"""Enough to show each figure gets its own: saving all sixteen atlases takes a minute."""
FIGURES = [PLAYER_ID, *(figure_id(c) for c in SOME)]
ORANGE_PISTOL = (250, 130, 20)


class Pointing:
    """Keeps what it's given, with an orange pistol held out to the right."""

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        out = images[0].copy()
        at = np.flatnonzero((np.asarray(out) != GROUND).any(axis=2).any(axis=0))[-1]
        y = SIZE[1] // 2
        ImageDraw.Draw(out).rectangle((at, y, at + 120, y + 30), ORANGE_PISTOL)
        return out


@contextmanager
def pointing() -> Iterator[Pointing]:
    yield Pointing()


@pytest.fixture
def content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(aim, "COMBINATIONS", SOME)
    for figure in FIGURES:
        for suffix in ("json", "webp"):
            shutil.copy(CONTENT / f"{figure}.{suffix}", tmp_path)
    return tmp_path


def manifest(directory: Path, who: str) -> dict:
    return json.loads((directory / f"{who}.json").read_text())


def aimed(directory: Path, found: dict) -> Image.Image:
    entry = found["frames"][aim.FRAME]
    with Image.open(directory / entry["atlas"]) as sheet:
        return sheet.convert("RGBA")


def added(directory: Path) -> None:
    aim.aim(Cached(pointing, None), directory, keyed, lambda _: None)


def test_every_figure_gains_the_aim_with_a_muzzle_at_the_end_of_the_pistol(content: Path) -> None:
    added(content)

    for who in FIGURES:
        found = manifest(content, who)
        picture = aimed(content, found)
        assert found["aimed"] == aim.fingerprint()
        assert found["poses"][aim.FRAME] == [aim.FRAME]
        ahead, level = found["frames"][aim.FRAME]["muzzle"]
        orange = aim.pistol(picture)
        assert ahead == np.flatnonzero(orange.any(axis=0))[-1] + 1
        assert orange[level].any()


def test_adding_it_leaves_the_other_frames_where_they_are(content: Path) -> None:
    def others(who: str) -> dict:
        frames = manifest(content, who)["frames"]
        return {name: entry for name, entry in frames.items() if name != aim.FRAME}

    before = {who: others(who) for who in FIGURES}
    atlases = {who: (content / f"{who}.webp").read_bytes() for who in FIGURES}

    added(content)

    assert {who: others(who) for who in FIGURES} == before
    assert {who: (content / f"{who}.webp").read_bytes() for who in FIGURES} == atlases


def test_adding_it_again_changes_nothing(content: Path) -> None:
    added(content)
    once = {path.name: path.read_bytes() for path in content.iterdir()}

    added(content)

    assert {path.name: path.read_bytes() for path in content.iterdir()} == once


def test_a_figure_with_nothing_fitted_is_the_painting_alone_and_one_with_parts_shows_them(
    content: Path,
) -> None:
    added(content)

    plain = aimed(content, manifest(content, PLAYER_ID))
    worn = aimed(content, manifest(content, figure_id(SOME[-1])))
    assert {"feet", "datajack", "eye"} <= set(missing(plain, SOME[-1], "stand", 0.7))
    feet = manifest(content, figure_id(SOME[-1]))["frames"][aim.FRAME]["feet"]
    assert missing(aim.unarmed(worn, feet), SOME[-1], "stand", 0.7) == []


@pytest.mark.parametrize(("name", "value"), [("WORDS", "other words"), ("REROLL", 1)])
def test_a_new_prompt_or_reroll_is_a_new_fingerprint(
    monkeypatch: pytest.MonkeyPatch, name: str, value: object
) -> None:
    before = aim.fingerprint()

    monkeypatch.setattr(aim, name, value)

    assert aim.fingerprint() != before
