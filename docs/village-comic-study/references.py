"""The new clean references: #329's street and interior scenes, painted from text in each line.

`python references.py [line/scene=seed …]` paints those candidates, or every kept one that's
missing, into out/references/. `python references.py keep` copies the kept seeds into
references/<line>/. Each candidate is looked at for lettering before it's kept.
"""

import time

from PIL import Image
from study import LINES, OUT, STUDY, args, log, study2, styled, wait_for_gpu

SIZE = (1344, 768)
SCENES = ("street", "interior")
"""#329's `signage` isn't painted: no piece takes it, since fronts are painted from plans alone."""
KEPT = {
    "a/street": 46,
    "a/interior": 42,
    "b/street": 42,
    "b/interior": 43,
}
"""The seed kept for each reference."""
REJECTED = {
    "a-street-42-v1": "print on a shirt",
    "a-street-44-v1": "a blade sign",
    "a-interior-42-v1": "shop signs behind",
    "a-interior-44-v1": "a machine's display",
    "b-interior-42-v1": "shop signs behind",
    "b-interior-44-v1": "a shop sign behind",
    "a-street-42-v2": "print on a hoodie",
    "a-street-43-v2": "print on a hoodie",
    "a-street-44-v2": "print on a hoodie",
    "a-street-45-v2": "glyphs on a sign band",
    "b-interior-42-v2": "a machine's buttons",
}
"""Every candidate rejected for lettering, and where it was. The rest were kept or unused."""
PLAIN = {
    "street": " The clothes are plain, with no prints, and no shop has a blade sign.",
    "interior": " Behind the building only sky, distant glass towers and trees, with no shops and "
    "no signs. Every machine and screen is plain, with nothing written on it.",
}
"""Added after the first seven candidates, all but one rejected for lettering: on a shirt, a
blade sign, an espresso machine's display, and shop signs behind the dollhouse."""
VERSION = 2


def prompt(line, scene: str) -> str:
    common = study2("common")
    words = study2("references")
    subject = words.SCENES[scene].format(
        period=common.PERIOD, city=words.CITY, clothes=common.CLOTHES
    )
    return styled(f"{subject}{PLAIN[scene]} {line.whole}", line)


def candidate(key: str, seed: int):
    return OUT / "references" / f"{key.replace('/', '-')}-{seed}-v{VERSION}.png"


def paint(todo: list[tuple[str, int]]) -> None:
    from simile.dolls.flux import Flux

    with Flux(before_load=wait_for_gpu) as flux:
        for key, seed in todo:
            path = candidate(key, seed)
            if path.exists():
                continue
            line, scene = key.split("/")
            start = time.perf_counter()
            image = flux.paint(prompt(LINES[line], scene), SIZE, seed)
            seconds = round(time.perf_counter() - start, 1)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path)
            log({"event": "paint", "key": f"references/{key}", "seed": seed, "seconds": seconds})
            print(f"{key} seed {seed}: {seconds} s", flush=True)


def keep() -> None:
    for key, seed in KEPT.items():
        line, scene = key.split("/")
        target = STUDY / "references" / line / f"{scene}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.open(candidate(key, seed)).convert("RGB").save(target, quality=86, optimize=True)


def main(argv: list[str]) -> None:
    if argv == ["keep"]:
        keep()
        return
    todo = list(KEPT.items())
    if argv:
        todo = [(a.split("=")[0], int(a.split("=")[1])) for a in argv]
    paint(todo)


if __name__ == "__main__":
    main(args())
