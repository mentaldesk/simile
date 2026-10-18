from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import Field

from simile.cafe.menu import Drink, Menu
from simile.conversation.prompt import first_name
from simile.conversation.script import third_person
from simile.npc.generate import first_sentence
from simile.schema import Id, Line, Npc, Relationship
from simile.schema import Model as Schema
from simile.social import describe

MAX_WORDS = 25


class Order(Schema):
    """The barista's answer to the player at the counter."""

    says: str = Field(
        description=f"Your spoken reply: one or two short sentences, at most {MAX_WORDS} words, "
        "plain speech with no stage directions or quotation marks."
    )
    drink: str | None = Field(
        description="The drink you'll make, as you'd call it out when it's ready, e.g. "
        '"oat flat white". Null if they haven\'t asked for a drink you can make.'
    )
    menu: str | None = Field(
        description="The menu id of the drink it's made as, or null for something off the menu."
    )


class Said(Schema):
    by: Literal["barista", "customer"]
    text: str = Field(description=f"Plain speech, at most {MAX_WORDS} words.")


class Exchange(Schema):
    """A resident ordering at the counter."""

    lines: list[Said] = Field(min_length=2, max_length=6)
    drink: str = Field(description="What the customer orders, as the barista would call it out.")
    menu: str | None = Field(
        description="The menu id of the drink it's made as, or null for something off the menu."
    )


def barista_system(barista: Npc, menu: Menu) -> str:
    return "\n\n".join(
        [
            f"You are {barista.name}, aged {barista.age}, the barista at the Daily Grind, a coffee "
            "shop in a small, modern village. Stay in character.",
            barista.persona,
            f"How you speak: {barista.speaking_style}",
            f"You're behind the counter, taking an order. The menu: {menu.listing()}. You can also "
            "make any other drink a café could, or a variation like oat milk, an extra shot or "
            "decaf. If they ask for something a café couldn't make, say so kindly and suggest "
            "something you can.",
        ]
    )


def order_prompt(
    barista: Npc, lines: Sequence[Line], names: Mapping[Id, str], feelings: Relationship
) -> str:
    customer = names.get(feelings.about, "the customer")
    transcript = "\n".join(
        f"{names.get(line.speaker, line.speaker)}: {line.text}" for line in lines
    )
    return f"""\
The customer is {customer}, a newcomer to the village. {describe(feelings, customer)}

The conversation so far:
{transcript}

Reply as {first_name(barista)}. If they've asked for a drink you can make, confirm it in your \
own words and give it as `drink`. Otherwise answer them, ask what they'd like, and leave `drink` \
null."""


EXCHANGE_SYSTEM = """\
You write short exchanges at the counter of the Daily Grind, the coffee shop in a small, modern \
village, between its barista and a resident ordering. They're neighbours: keep it natural and \
brief, true to how each of them speaks and feels about the other, in plain British English. No \
stage directions, quotation marks or narration."""


def exchange_prompt(
    barista: Npc,
    customer: Npc,
    feelings: Mapping[Id, Relationship],
    usual: Drink,
    menu: Menu,
    now: datetime,
) -> str:
    def side(npc: Npc, role: str, other: Npc) -> str:
        felt = third_person(
            describe(feelings[npc.id].model_copy(update={"flags": []}), first_name(other)),
            first_name(npc),
        )
        return (
            f"The {role}: {npc.name}, {npc.age}, {npc.occupation}. {first_sentence(npc.persona)} "
            f"How they speak: {npc.speaking_style} {felt}"
        )

    return f"""\
{side(barista, "barista", customer)}

{side(customer, "customer", barista)}

It's {now:%H:%M}. The menu: {menu.listing()}. {first_name(customer)} usually has a {usual.name}.

Write two to five lines: the barista greets them, they order (most likely their usual, though \
anything a café could make is fine), maybe a line of small talk that suits them both, and the \
barista confirms. Each line at most {MAX_WORDS} words."""
