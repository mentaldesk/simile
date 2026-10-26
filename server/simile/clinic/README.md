# simile.clinic

S7: the clinic in the old metro's depot, and the tunnel doctor who runs it. Its `running` hook makes
a `Clinic` and a `DoctorTalk`, adds the doctor's trade to the clinic's buyer, puts the doctor in the
snapshot and ticks their talk on the sim loop.

## The doctor

Annelie Joubert, a struck-off Apex surgeon, is `content/npcs/tunnels/annelie.json`: an `Npc` with
values, a persona and a voice, but not a resident. `load_npcs` reads only `content/npcs/*.json`,
so she isn't in `Behaviour`, the economy's residents, gossip, reflection or the incident, and
residents' days are as they were. She stands at the clinic's `clinic_doctor` spot, in every
snapshot (`standing`), and never moves.

Her figure is painted like a resident's (`simile dolls paint annelie`), and her greetings recorded
like theirs (`simile greetings annelie`): both commands read her through `load_doctor()`.

## What she buys and fits

`ClinicConfig` holds every price, recipe and the stock. They're sim facts: the doctor voices them,
and nothing said to her changes them. She buys a kidney for 100, one while they have both, and
salvage at the economy's prices (`simile.player`'s *Selling*).

**From recipes** (P4). Every stage 2 bionic is a `Procedure` in `procedures`: its `Recipe` (P1),
what it does, for her to say, and what she pays for the recipe. She builds one only for a player
who knows its recipe (`Player.mind`), for its credits and the parts it lists, which the fitting uses
up, and only once everything in its `after` is fitted: the power cell, for everything but a cell.
Each `Fitting` is built from its recipe, so the two can't drift. She fits none their cell can't run
(`simile.player`'s *Power*): past its limit, the next one waits for a bigger cell.

| Bionic | In place of | Credits | Parts | She buys the recipe for |
|---|---|--:|---|--:|
| Power cell | The stomach | 100 | 3 lithium cell, 1 charge controller | — |
| Datajack | A vertebra | 100 | 3 copper wire, 1 USB-C connector | 15 |
| Bionic legs | The legs | 150 | 2 pump impeller, 1 copper coil | 25 |
| Spring feet | The feet | 150 | 2 brass fitting, 1 float valve | 25 |
| Infrared eye | Either eye | 200 | 1 infrared lens | 30 |
| Power cell, grade 2 | The stomach | 250 | 4 old battery, 2 copper coil | 40 |
| Bionic legs, grade 2 | The legs | 300 | 2 pump impeller, 2 servo motor | 45 |
| Spring feet, grade 2 | The feet | 300 | 2 pressure gauge, 3 brass fitting | 45 |
| Power cell, grade 3 | The stomach | 600 | 6 old battery, 1 Apex board | 90 |
| Bionic legs, grade 3 | The legs | 700 | 1 Apex actuator, 2 servo motor | 105 |

A higher grade goes in place of the player's own part or a lower grade of its line, which she
takes back. Where each recipe and its parts are found is `content/street/README.md`'s *Finds*;
she tells the player the power cell's as they walk in (`simile.player`'s *Finds*).

**Selling recipes.** She buys each recipe they know once, for its one-off sum. They still know it,
and she still builds from it. She won't buy the power cell's, which she teaches.

**Stage 1's legs** (#389) are `offers`, fitted for their price alone until P18 retires them: the
hydraulic and sprint legs (80) in place of the player's own, then the spring and blade legs (240)
in place of each, and the premium legs (600) in place of either, with an Apex actuator they bring.
`street/jump.py` says what each does. Each goes in place of the legs before it (`Offer.after`),
which she takes back, and the premium legs are offered only while they carry the actuator.

She has one of each bionic (`stock`), so once fitted it's gone.

- `Clinic.keep` adds `parts`, `fittings` and `recipes` to the clinic's `player_state` buyer,
  through `simile.player`'s `keepers_of(app)`: what she'd buy of their body now, each bionic she'd
  fit, whether or not they can pay or have the parts, with the parts of their body it can go in
  place of, and what she'd pay for each recipe they know.
- The `lifespan` hook adds every recipe to `simile.player`'s `recipes_of(app)`, before any
  module's `running` reads it, so `player_state` carries each one they know in full.
- `sell_part` sells a kidney, and `sell_recipe` a recipe: the economy pays the player from
  `OUTSIDE` as `salvage` at the clinic, and the part is `sold`, or the recipe is in `mind.sold`.
- `fit` takes the price from the player to `OUTSIDE` as a `purchase` at the clinic, uses up the
  parts, and the bionic goes in place of the part. Nothing happens if they can't pay or are short
  of a part, so `Economy.pay` never raises.
- They only work in the clinic. The next `player_state` follows on the sim loop.

## Talking to her

`DoctorTalk` is the player's conversation with her, written through L1 like any resident's reply
but outside B2's engine, which only knows residents. It publishes `ConversationStarted`,
`LineSpoken` and `ConversationEnded`, so the client shows it like any other.

- **Greeting.** When the player walks into the clinic, she opens a conversation, at most every
  `greet_every` (2) sim hours, so the client plays one of her greetings. Walking in warms an L1
  process with her system prompt.
- **Replies.** `player_say` to her, while in the clinic, gets a reply at the player's priority, one
  sentence a line, paced by each line's length.
- **Ending.** It ends when they walk out, or after `silence` (60) sim seconds with nothing said.
- **The prompt.** The system prompt is who she is, her fixed prices for a kidney and salvage, how
  she builds from recipes, and stage 1's legs, with no haggling: no menu of every bionic. Each turn
  adds what she can see of them (their bionics, a sold kidney), what she'd buy or fit now, with
  the parts they're short of, the recipes they know that wait for the cell, and a bionic or two
  they don't know the recipe for, to hint at without a price. So what she says follows what they
  know. She never takes money in talk: the player trades at the counter, with E.

B2's `player_say` handler logs that it ignored a line to her, since she isn't a resident.

## Pricing

**The kidney pays for the power cell.** The cell's 100 credits are what the kidney fetches. On
their own legs the metro gives 65 in secrets, the stairwell's and the catwalk's, and 25 a round of
salvage, so two days of it, less two café meals a day, come to 95: not enough. A day of it and the
datajack's schematic, sold, don't either. `test_the_kidney_pays_for_the_cell_and_the_metro_on_foot_doesnt_in_two_days`
checks it. The cell's parts, from P6, cost nothing but finding them.

Each grade of a line costs more than the one before. Recipes sell for about 15% of what
they cost to build, so selling one is a little money now, never the way to a bionic.

Stage 1's legs keep S15's prices: a grade 2 costs three times a grade 1 and more than the eye, and
premium two and a half times that. `test_each_grade_of_the_old_legs_costs_steeply_more_than_the_one_before`
checks the steps.
