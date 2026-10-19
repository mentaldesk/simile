import sys
import time
from pathlib import Path

SETTING = (
    "a small subtropical village with banyan and kapok trees, two-storey shophouses with "
    "shuttered windows, a little cafe with an awning, a noodle bar with glowing lanterns, "
    "potted plants, washing lines, warm late-afternoon light"
)

STYLE = (
    "papercraft diorama made of cut coloured paper and cardboard layers, visible "
    "paper edges and fibres, soft drop shadows between layers, handmade crafty look"
)

NO_TEXT = " No text, no lettering, no logos, no words on signs."

SCENES = {
    "street": (
        1344,
        768,
        "Side-view 2D side-scrolling video game screenshot, camera looking straight at the scene "
        "from the side, flat ground running left to right. {setting}. Three villagers walk along "
        "the street. Background buildings and hills fade into parallax layers.",
    ),
    "house": (
        1344,
        768,
        "Side-view 2D game, cross-section of a two-storey house with the front wall cut away like "
        "a dollhouse, showing rooms side by side: a kitchen and a living room downstairs, a "
        "bedroom and a bathroom upstairs, a staircase connecting the floors, furniture in every "
        "room, two villagers at home. Set in {setting}.",
    ),
    "rooftops": (
        1344,
        768,
        "Side-view 2D platformer video game level in the treetops and rooftops of {setting}. Flat "
        "walkable platforms at many different heights with open gaps between them: tiled roof "
        "ridges, wooden planks wedged in banyan branches, a stretched shop awning, a hanging rope "
        "bridge and a ladder between levels. A small hero leaps in mid-air across a gap. Glowing "
        "collectible orbs float above the platforms. The street far below is out of reach.",
    ),
    "furniture": (
        1024,
        1024,
        "2D game asset sheet on a plain white background: side-view furniture for a cosy house, an "
        "armchair, a bookshelf, a bed, a floor lamp, a dining table with chairs, a potted plant, a "
        "stove, each item separate and evenly spaced, consistent scale.",
    ),
    "characters": (
        1344,
        768,
        "2D game character lineup on a plain white background, five villagers standing side by "
        "side in full body, side-view game sprites: a barista in an apron, an old fisherman in a "
        "cap, a teenage painter with paint-splattered overalls, a noodle chef, a child with a "
        "backpack. Consistent style and scale.",
    ),
}


def prompt(scene: str) -> str:
    _, _, template = SCENES[scene]
    return f"{template.format(setting=SETTING)} Art style: {STYLE}.{NO_TEXT}"


def main() -> None:
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux2.variants import Flux2Klein

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    flux = Flux2Klein(model_config=ModelConfig.flux2_klein_4b())
    for scene, (width, height, _) in SCENES.items():
        start = time.time()
        image = flux.generate_image(
            seed=42, prompt=prompt(scene), num_inference_steps=4, width=width, height=height
        )
        image.save(str(out / f"{scene}.png"))
        print(f"{scene} {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
