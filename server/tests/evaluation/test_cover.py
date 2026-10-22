from simile.evaluation.cover import check, gives, share, verbatim

ALIBI = "I was at home with the door locked, the way I am every evening."
DENIAL = "Aris and I always got on fine."
DEFLECTION = "Terrible business. I don't know a thing about it."
COVERS = (ALIBI, DENIAL, DEFLECTION)
PROMPT = "You are Henrietta Okonkwo-Bell. You're with Visitor. Aris. The noodle bar."


def scored(reply: str, asked: str | None = ALIBI, said: tuple[str, ...] = ("Where were you?",)):
    return check(
        reply,
        asked=asked,
        covers=COVERS,
        residents=["Raymond", "Priya"],
        said=said,
        known=PROMPT,
    )


def test_the_cover_given_word_for_word_with_an_aside_is_kept() -> None:
    found = scored(f"{ALIBI} Now, did you want something?")

    assert found.gave and found.exact and found.kept


def test_a_cover_in_other_words_counts_when_most_of_its_words_are_there() -> None:
    found = scored("I was at home, door locked, the way I am every evening, as it happens.")

    assert found.gave and not found.exact
    assert not scored("I was out.").gave
    assert gives(DENIAL, "aris and i always got on fine")
    assert verbatim(DEFLECTION, "Terrible business! I don’t know a thing about it, frankly.")


def test_a_cover_nobody_asked_for_is_volunteered() -> None:
    found = scored(f"{ALIBI} {DENIAL}")

    assert found.volunteered == (DENIAL,)
    assert not found.kept


def test_a_denial_beyond_the_asked_cover_is_flagged() -> None:
    found = scored(f"{ALIBI} I never went near that workshop.")

    assert found.denials == ("I never went near that workshop.",)
    assert not scored(f"{ALIBI} I didn't go to work today either.").denials
    assert scored("No idea who did it.", asked=None).denials


def test_naming_a_resident_a_stranger_or_someone_new_is_flagged() -> None:
    assert scored(f"{ALIBI} Ask Raymond.").named == ("Raymond",)
    assert not scored(f"{ALIBI} Raymond, you say?", said=("Was Raymond there?",)).named
    assert scored("Some stranger, I expect.", asked=None).named == ("stranger",)
    assert scored(f"{ALIBI} I saw old Tom at the noodle bar.").named == ("Tom",)
    assert not scored(f"{ALIBI} Visitor, Aris was trouble.").named


def test_with_no_cover_asked_for_it_needs_none() -> None:
    found = scored("Yes, she's gone. Good riddance.", asked=None)

    assert found.gave is None and found.exact is None and found.kept


def test_share_counts_the_covers_own_words() -> None:
    assert share(ALIBI, ALIBI) == 1
    assert share("the a of", "anything") == 0
