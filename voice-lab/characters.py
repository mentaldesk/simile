from pathlib import Path

OUT = Path(__file__).parent / "out"
VOICES = Path(__file__).parent / "voices"

CHARACTERS = {
    "dwarf_smith": {
        "voice": (
            "An old male dwarf blacksmith in his seventies. Deep, gravelly, slightly wheezy voice "
            "with a thick Scottish accent. Speaks slowly and deliberately, gruff but warm."
        ),
        "reference": "Aye, I've been working this forge for nigh on fifty years. Iron doesn't lie to you, not like people do.",
        "lines": [
            "You're not from around here, are you? Your boots are far too clean.",
            "That blade? Hah! I wouldn't use it to butter my bread. Leave it with me till morning.",
            "The mines went quiet three winters ago. Nobody who went down to find out why came back up.",
        ],
    },
    "nervous_innkeeper": {
        "reference_audio": VOICES / "theater_witch.wav",
        "reference": (
            "Oohh, me bones ache in the mornings... what I really need is a little boy or a little girl on toast, "
            "with a bit of hot butter and coffee."
        ),
        "lines": [
            "No, no, nobody's been asking about you. Why would anyone be asking about you?",
            "The stew's mostly turnip tonight, I'm afraid. The butcher didn't come by. He hasn't come by all week, actually.",
            "If you hear anything in the cellar tonight, it's just the barrels settling. Just the barrels.",
        ],
    },
}


def reference_path(name: str) -> Path:
    return CHARACTERS[name].get("reference_audio", VOICES / f"{name}.wav")
