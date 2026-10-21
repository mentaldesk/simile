"""Approach 3: 3D models, built in Blender with MPFB from each resident's `Appearance`, posed by
the client's joint angles and rendered toon-shaded and side-on.

`python model.py [who …]` builds and renders each resident into out/model/<who>/, through
`blender.sh` and `mpfb/build.py`.
"""

import json
import subprocess
import sys
import time

import poses
from study import OUT, STUDY, WHO, log, look_of, people

FOLDER = OUT / "model"
GRIME = FOLDER / "grime.png"
SIZE = (512, 768)
PPM = 300
"""Pixels a metre at full size: a resident about 560 px tall, as #310's atlases draw them."""
LINE = 4.0
PROPORTIONS = {"head": 1.9, "legs": 0.72, "body": 0.85, "neck": 0.6, "arms": 0.82}
"""Bone scales that give the model #329's grimy proportions, its head about as big a share of
its height as #329's dolls' heads at 1.6 times #310's."""
HAIR = {
    "buzz": "short04",
    "short": "short02",
    "curly": "afro01",
    "bob": "bob01",
    "long": "long01",
    "ponytail": "ponytail01",
    "bun": "short02",
    "bald": None,
}
"""Each hair style's CC0 MakeHuman hair. A bun adds a ball of hair to the back of the head."""
WEIGHT = {"slim": (0.3, 0.45), "average": (0.5, 0.5), "broad": (0.72, 0.68)}
"""Each build's MPFB weight and muscle."""


def npc(who: str) -> dict:
    from simile.npc.content import NPCS_DIR

    return json.loads((NPCS_DIR / f"{who}.json").read_text())


def macro(who: str) -> dict:
    """MPFB's sliders. The `Appearance` gives the build; age and gender come from the resident's
    record and voice, which the character creator doesn't have."""
    record = npc(who)
    age = record["age"]
    words = record["voice"]["description"].lower()
    gender = 0.0 if " woman" in words or "woman " in words else 1.0
    weight, muscle = WEIGHT[people()[who].build.value]
    return {
        "gender": gender,
        "age": 0.5 + (min(age, 90) - 25) / 65 * 0.5
        if age >= 25
        else 0.1875 + (age - 11) / 14 * 0.3125,
        "muscle": muscle,
        "weight": weight,
        "proportions": 0.5,
        "height": 0.5,
        "cupsize": 0.5,
        "firmness": 0.5,
        "race": {"asian": 0.33, "caucasian": 0.33, "african": 0.33},
    }


def frames() -> list[dict]:
    out = [
        {"name": f"walk-{i}", "view": "side", "angles": poses.walk(i / poses.WALK_FRAMES)}
        for i in range(poses.WALK_FRAMES)
    ]
    out += [
        {"name": "stand", "view": "side", "angles": poses.STAND},
        {"name": "front", "view": "front", "angles": poses.STAND},
        {"name": "back", "view": "back", "angles": poses.STAND},
        {"name": "sit", "view": "side", "angles": poses.sitting()},
    ]
    out += [
        {"name": f"stairs-{i}", "view": "side", "angles": poses.stairs(i / 4)} for i in range(4)
    ]
    out += [
        {
            "name": f"ladder-{i}",
            "view": "back",
            "angles": poses.ladder_from_side(i / 4),
            "plant": False,
        }
        for i in range(4)
    ]
    return out


def spec(who: str) -> dict:
    look = look_of(who)
    appearance = people()[who]
    colours = {
        "skin": look.skin,
        "hair": look.hair,
        "top": look.top,
        "bottom": look.bottom,
        "shoe": look.shoe,
        "accent": look.accent,
        "apron": look.apron,
    }
    return {
        "who": who,
        "macro": macro(who),
        "colours": {k: list(v) for k, v in colours.items()},
        "hair": HAIR[appearance.hair_style.value],
        "bun": appearance.hair_style.value == "bun",
        "accessories": sorted(a.value for a in appearance.accessories),
        "proportions": PROPORTIONS,
        "size": list(SIZE),
        "ppm": PPM,
        "line": LINE,
        "stand": poses.STAND,
        "frames": frames(),
        "save_blend": True,
        "grime": "../grime.png" if GRIME.exists() else None,
    }


def build(who: str, only: set[str] | None = None, folder=None) -> None:
    folder = folder or FOLDER / who
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "spec.json"
    made = spec(who)
    if only:
        made["frames"] = [f for f in made["frames"] if f["name"] in only]
    path.write_text(json.dumps(made, indent=1))
    start = time.perf_counter()
    run = subprocess.run(
        [
            str(STUDY / "blender.sh"),
            "-b",
            "--python-exit-code",
            "1",
            "-P",
            str(STUDY / "mpfb" / "build.py"),
            "--",
            str(path),
            str(folder),
        ],
        capture_output=True,
        text=True,
    )
    (folder / "blender.log").write_text(run.stdout + run.stderr)
    if run.returncode:
        print(run.stdout[-3000:], run.stderr[-3000:])
        raise SystemExit(f"Blender failed for {who}")
    seconds = round(time.perf_counter() - start, 1)
    timings = json.loads((folder / "timings.json").read_text())
    log({"event": "blender", "approach": "model", "key": who, "seconds": seconds, **timings})
    print(f"{who}: {seconds} s in all, build {timings['build']} s", flush=True)


if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = next((set(a[7:].split(",")) for a in sys.argv[1:] if a.startswith("--only=")), None)
    for name in names or WHO:
        build(name, only, OUT / "model-test" / name if only else None)
