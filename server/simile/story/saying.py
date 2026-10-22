import re

PUNCTUATION = re.compile(r"[^\w\s]+")


def plain(text: str) -> str:
    """`text` in lower case, with its punctuation, quotes and apostrophes as single spaces."""
    return " ".join(PUNCTUATION.sub(" ", text.casefold()).split())


def says(said: str, words: str) -> bool:
    """Whether `said` holds `words` word for word, whatever their case, quotes and punctuation."""
    wanted = plain(words)
    return bool(wanted) and f" {wanted} " in f" {plain(said)} "
