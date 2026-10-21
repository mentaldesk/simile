"""The style references: four scenes in each style, painted from text alone.

`python references.py [style …] [--seed name=n …]` paints what's missing into references/<style>/.
"""

import sys
import time

from common import CLOTHES, OUT, PERIOD, STYLES, Style, TextPainter, log, reference, styled

SIZE = (1344, 768)
SEEDS = {"papercraft/signage": 43, "cartoon/interior": 43}
"""`<style>/<scene>` to a seed other than 42, for a reference repainted after a look."""

SCENES = {
    "street": (
        "Side-view 2D side-scrolling video game screenshot, camera looking straight at the scene "
        "from the side, flat pavement running left to right. The street of {period}. Three "
        "residents in {clothes} walk along the pavement. The towers and trees behind fade into "
        "parallax layers. No shop has a name board, banner or poster: each shows one glowing "
        "neon pictogram in its window, a coffee cup, a noodle bowl or a gear."
    ),
    "interior": (
        "Side-view 2D game, a cross-section of a three-storey building with its whole front wall "
        "removed like a dollhouse, so every room is open to view, seen straight on: a modern "
        "coffee bar with an espresso machine on the ground floor, a maker space with a 3D "
        "printer, a laser cutter and a workbench on the middle floor, and a small modern flat "
        "with a sofa, a bed and a kitchenette on the top floor, stairs between the floors, LED "
        "strip lights, potted plants, two residents at work. A contemporary building in {city}."
    ),
    "residents": (
        "2D game character lineup on a plain white background with nothing behind them, five "
        "residents of {city} standing side by side in full body: a young barista with light "
        "brown skin in a t-shirt and an apron, an older man with pale skin in a polo shirt and "
        "a cap, a student with dark brown skin in a hoodie with headphones, a woman with golden "
        "tan skin in a light jacket and jeans with a backpack, and an older woman with deep "
        "brown skin and grey hair in a bun, in a cardigan. {clothes}. Consistent style and scale."
    ),
    "signage": (
        "The front of a small corner shop at dusk, seen straight on, in {period}. Glowing neon "
        "tubes bent into simple pictures of a coffee cup, a noodle bowl and a gear, a light "
        "panel glowing in plain colour, a glass shopfront lit from inside, an air-conditioning "
        "unit, potted plants and a parked e-bike."
    ),
}
CITY = "a modern southern Chinese tech city like Shenzhen"


def prompt(scene: str, style: Style) -> str:
    subject = SCENES[scene].format(period=PERIOD, city=CITY, clothes=CLOTHES)
    return styled(f"{subject} {style.whole}", style)


def main(args: list[str]) -> None:
    seeds = dict(SEEDS)
    names = []
    for arg in args:
        if arg.startswith("--seed="):
            key, _, n = arg.removeprefix("--seed=").partition("=")
            seeds[key] = int(n)
        else:
            names.append(arg)
    todo = [
        (style, scene)
        for style in (STYLES[n] for n in names or STYLES)
        for scene in SCENES
        if not reference(style, scene).exists()
    ]
    if not todo:
        return
    with TextPainter() as painter:
        for style, scene in todo:
            seed = seeds.get(f"{style.name}/{scene}", 42)
            start = time.perf_counter()
            image = painter.paint(prompt(scene, style), SIZE, seed)
            seconds = round(time.perf_counter() - start, 1)
            raw = OUT / "references" / f"{style.name}-{scene}-{seed}.png"
            raw.parent.mkdir(parents=True, exist_ok=True)
            image.save(raw)
            path = reference(style, scene)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path, quality=86, optimize=True)
            key = f"references/{style.name}/{scene}"
            log({"event": "paint", "key": key, "kind": "reference", "seconds": seconds})
            print(f"{style.name}/{scene} seed {seed}: {seconds} s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
