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

`ClinicConfig` holds every price and the stock. They're sim facts: the doctor voices them, and
nothing said to her changes them.

| | Price | And |
|---|--:|---|
| A kidney, bought | 100 | One, while they have both |
| Hydraulic legs | 80 | Their legs |
| Sprint legs | 80 | Their legs |
| Spring legs | 240 | The hydraulic legs |
| Blade legs | 240 | The sprint legs |
| Premium legs | 600 | The spring or blade legs, and an Apex actuator |
| Datajack | 150 | A vertebra |
| Infrared eye | 200 | Either eye |

She has one of each bionic (`stock`), so once fitted it's gone. What's in stock is the stock less
what the player has fitted, so nothing more is saved. She buys salvage too, at the economy's prices
(`simile.player`'s *Selling*).

**Legs come in grades** (#389), two branches and then premium, each a bionic in place of the legs.
`street/jump.py` says what each does. The hydraulic and sprint legs go in place of the player's
own. Each grade after them goes in place of the legs before it (`Offer.after`), which she takes
back, so she stocks the next grade only once the one before is fitted and a branch, once chosen,
is the way to premium. The premium legs also need a part they bring (`Offer.needs`), the Apex
actuator, which only S9's sewers will hold (`simile.street.sewers.APEX_ACTUATOR`). She offers them
only while they carry it, and the fitting uses it up.

- `Clinic.keep` adds `parts` and `fittings` to the clinic's `player_state` buyer, through
  `simile.player`'s `keepers_of(app)`: what she'd buy of their body now, and each bionic she'd fit,
  with the parts it can go in place of that are still theirs, or the legs an upgrade follows.
- `sell_part` sells a kidney: the economy pays the player from `OUTSIDE` as `salvage` at the
  clinic, and the part is `sold`.
- `fit` takes the price from the player to `OUTSIDE` as a `purchase` at the clinic, and the bionic
  goes in place of the part. Nothing happens if they can't pay, so `Economy.pay` never raises.
- Both only work in the clinic. The next `player_state` follows on the sim loop.

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
- **The prompt.** The system prompt is who she is and the clinic's fixed price list, with no
  haggling. Each turn adds what she can see of them (their bionics, a sold kidney) and what she'd
  buy or fit now, so what she says follows the sim. She never takes money in talk: the player
  trades at the counter, with E.

B2's `player_say` handler logs that it ignored a line to her, since she isn't a resident.

## Pricing

The prices carry S15's loop: a kidney, then a round of the metro's salvage with daily respawns,
and its secrets, against meals at 5–10. The kidney buys the hydraulic legs with 20 over. On them a
round is worth 43, all but the valve up in the alcove, and the secrets they reach 125: the
stairwell's, the catwalk's and the high ledge's. Those and two days' rounds, less two café meals a
day, buy the datajack with 61 over. The eye then takes about four days of the metro alone, which
the sewers (S9) should shorten. `test_the_prices_carry_s15s_loop` checks it.

The upgrades rise steeply and wait for the loop. A grade 2 costs three times a grade 1 and more
than the eye: about seven days of the metro's rounds, less meals, after the eye. Premium costs two
and a half times that, about fifteen days of rounds on the spring legs, and the part from the
sewers. The sprint branch reaches less of the metro's salvage, 25 a round, so it leans on the
sewers more. `test_each_grade_of_legs_costs_steeply_more_than_the_one_before` checks the steps.
