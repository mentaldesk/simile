DESIGNABLE = frozenset({"American"})
"""Accents VoiceDesign can do. N2b (#80) heard almost every other accent come out American."""
LOCAL = "A local accent, with nothing of anywhere else in it."


def accent_sentence(accent: str | None) -> str:
    """The first sentence of a voice description, which VoiceDesign follows best."""
    if accent is None:
        return LOCAL
    if accent.startswith("from "):
        return f"An accent {accent}."
    head, _, rest = accent.partition(", ")
    article = "An" if head[0] in "AEIOU" else "A"
    return f"{article} {head} accent{f', {rest}' if rest else ''}."


def needs_recording(accent: str | None) -> bool:
    return accent is not None and accent not in DESIGNABLE
