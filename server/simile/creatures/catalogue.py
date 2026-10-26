"""What each creature is painted from: its first frame from words, in the tunnels' cartoon, and
every other frame an edit of a frame before it, over a guide drawn from that frame."""

from dataclasses import dataclass, field

from simile.papercraft.painter import cartoon, grimy

Box = tuple[float, float, float, float]
"""Left, top, right and bottom, as shares of the frame's figure: (0, 0) its top-left corner and
(1, 1) its bottom-right."""

LOOKS = {"cartoon": cartoon, "grimy": grimy}
LEAD = "Make a new picture in exactly the {look} style of the reference picture: 2D game sprite: "
ALONE = (
    " Seen exactly from the side, facing right, the whole body in the frame, alone on a plain "
    "flat light grey background with nothing else in the picture, and no shadow on the background."
)
REDRAW = (
    "Redraw image 1 as a finished picture of the same {who}, unchanged in every detail, the same "
    "colours and the same size, seen exactly from the side facing right{completing}: it is now "
    "{pose} Keep the background plain flat light grey, with no shadow on it."
)
COMPLETING = ", completing what is missing"


@dataclass(frozen=True)
class Edit:
    """A frame painted over a guide: its `base` frame's painting, with `rub`'s boxes painted
    out for FLUX to fill in and `mirror`'s box reflected down under itself, over the rest, then
    turned `turn` degrees clockwise."""

    pose: str
    base: str
    rub: tuple[Box, ...] = ()
    mirror: Box | None = None
    turn: float = 0.0
    hangs: bool = False
    """Hangs from its anchor, the top of its figure, rather than standing or flying there."""

    @property
    def guided(self) -> bool:
        return bool(self.rub or self.mirror)


@dataclass(frozen=True)
class Creature:
    id: str
    who: str
    """What the prompts call it."""
    words: str
    """Its first frame, `first`."""
    look: str
    """`LOOKS`: #329's cartoon, or its grimy version."""
    moves: str
    """`walk` stands on its anchor, the ground under the middle of its first frame; `fly` is
    held up by it, the middle of its first frame."""
    length: float
    """How wide its first frame is, in metres."""
    first: str
    edits: dict[str, Edit]
    poses: dict[str, list[str]]
    tries: int = 3
    rerolls: dict[str, int] = field(default_factory=dict)
    """A frame to a reroll number, for one that came out off-model by eye."""

    @property
    def frames(self) -> tuple[str, ...]:
        return (self.first, *self.edits)

    def prompt(self, frame: str) -> str:
        style = LOOKS[self.look]
        if frame == self.first:
            return style(LEAD.format(look=self.look) + self.words + ALONE)
        edit = self.edits[frame]
        completing = COMPLETING if edit.guided else ""
        return style(REDRAW.format(who=self.who, completing=completing, pose=edit.pose))


LEGS: Box = (-0.1, 0.55, 1.1, 1.3)

CREATURES = {
    "rat": Creature(
        "rat",
        "rat",
        "a scruffy sewer rat walking on all fours, chunky and round, with matted grey-brown fur, "
        "a long pink scaly tail, beady red eyes, big pink ears and yellow buck teeth, more a "
        "grubby pest than a threat, a little comical.",
        "cartoon",
        "walk",
        0.8,
        "stand",
        {
            "stride": Edit(
                "scurrying fast to the right in mid-stride: one front leg reaching far forward, "
                "one hind leg stretched far back, the body low and long.",
                "stand",
                rub=(LEGS,),
            ),
            "pass": Edit(
                "scurrying to the right in the other half of its stride: the front paws tucked "
                "under its chest and the hind feet gathered right under its belly.",
                "stand",
                rub=(LEGS,),
            ),
            "attack": Edit(
                "lunging forward to bite: its head thrust forward and up with its mouth wide open "
                "showing its yellow buck teeth, its front paws raised off the ground with little "
                "claws out.",
                "stand",
                rub=((-0.1, 0.5, 1.1, 1.3), (0.62, -0.1, 1.1, 1.3)),
            ),
        },
        {"stand": ["stand"], "walk": ["stride", "pass"], "attack": ["attack"]},
    ),
    "bot": Creature(
        "bot",
        "robot",
        "a small broken old recycler robot, a squat boxy rusty steel body with dented "
        "yellow-and-black hazard paint mostly worn away, a big open hopper on its back full of "
        "scrap, one single round flickering red camera eye, a long jointed grabber arm with a "
        "three-fingered claw, walking on two short stubby bent mechanical legs with flat feet, "
        "loose cables, patched plates and bolts, very old and badly repaired.",
        "grimy",
        "walk",
        1.7,
        "stand",
        {
            "step": Edit(
                "taking a clumsy limping step to the right: its front leg lifted high and forward "
                "with the knee bent, its back leg straight and planted.",
                "stand",
                rub=((-0.1, 0.78, 1.1, 1.3),),
            ),
            "attack": Edit(
                "attacking: its grabber arm reaching far forward and up with the claw opened wide "
                "to grab, its body leaning forward, its red eye glowing brightly, sparks from a "
                "joint.",
                "stand",
            ),
        },
        {"stand": ["stand"], "walk": ["step", "stand"], "attack": ["attack"]},
    ),
    "dog": Creature(
        "dog",
        "dog",
        "a huge, frightening, savage feral wild dog, as big as a wolf, with heavy shoulders and "
        "a big head, standing on all fours, ready to attack: mangy dark brown and black fur with "
        "bald patches and scars, hackles raised, head low, lips drawn back in a snarl over long "
        "yellow fangs, drool, glowing pale yellow eyes, a torn ear, ribs showing, a long lean "
        "powerful body.",
        "cartoon",
        "walk",
        2.2,
        "stand",
        {
            "run": Edit(
                "galloping flat out at full speed to the right: the body stretched long and low, "
                "both front legs reaching far forward and both hind legs stretched far back, all "
                "four paws off the ground, ears flat back, snarling, its glowing pale yellow eyes "
                "wide and its long yellow fangs bared.",
                "stand",
                rub=((-0.1, 0.5, 1.1, 1.3),),
            ),
            "run_pass": Edit(
                "galloping at full speed to the right in the gathered half of its stride: the "
                "back arched up, all four legs bunched together under its belly, all four paws "
                "off the ground, snarling, its glowing pale yellow eyes wide and its long yellow "
                "fangs bared.",
                "stand",
                rub=((-0.1, 0.5, 1.1, 1.3),),
            ),
            "attack": Edit(
                "leaping up and forward at its prey, rearing high: its body tilted up, its front "
                "legs raised high with claws spread, its jaws gaping wide open with long yellow "
                "fangs and drool.",
                "stand",
                rub=((-0.1, 0.5, 1.1, 1.3),),
            ),
        },
        {"stand": ["stand"], "run": ["run", "run_pass"], "attack": ["attack"]},
    ),
    "bat": Creature(
        "bat",
        "bat",
        "a scruffy cave bat flying with its leathery wings spread wide, a small round furry dark "
        "brown body, big pointed ears, beady red eyes, tiny white fangs, thin bony wing fingers "
        "with torn dark brown leathery membranes, tiny clawed feet tucked under its belly, more "
        "a nuisance than a threat, a little comical.",
        "cartoon",
        "fly",
        1.0,
        "glide",
        {
            "up": Edit(
                "flying with both wings raised high above its body in the upstroke, the wing tips "
                "pointing straight up.",
                "glide",
                rub=((-0.1, -0.2, 0.52, 0.6), (0.4, -0.2, 0.62, 0.3)),
            ),
            "down": Edit(
                "flying with both wings swept down below its body in the downstroke, the wing "
                "tips pointing down at the ground.",
                "up",
                mirror=(-0.1, -0.1, 0.56, 0.42),
            ),
            "attack": Edit(
                "diving down to bite: its head thrust forward and down, its mouth wide open with "
                "its fangs bared, its little clawed feet thrust forward, its wings swept back.",
                "glide",
                turn=25,
            ),
            "roost": Edit(
                "roosting asleep, hanging upside down by its little feet, its feet at the top and "
                "its head at the bottom, its wings folded and wrapped tightly around its body, "
                "its eyes closed.",
                "glide",
                rub=((-0.1, -0.2, 0.52, 0.6), (0.4, -0.2, 0.62, 0.3)),
                turn=90,
                hangs=True,
            ),
        },
        {"fly": ["up", "glide", "down", "glide"], "attack": ["attack"], "roost": ["roost"]},
    ),
}
