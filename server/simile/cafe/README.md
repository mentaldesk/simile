# simile.cafe

G1: the Daily Grind. A barista works its counter, and the player and the residents order from them.
`cafe_of(app)` returns the server's `Cafe`, which the `running` hook ticks on the sim loop. It also
makes the café B5's writer for the barista (see *The player orders*).

## The barista

The barista is whoever works at the café, the resident whose `workplace` is `coffee_shop`, else
whoever lives there. In a cast world that's the cast's barista: casting fills the barista role
first, and the role's shift is the café's hours (#235). In the default village it's Mirela Dragomir
(`content/npcs/mirela.json`), who lives above the shop. A world with nobody working or living there
has no barista, so nobody takes orders, but residents still sit down at the tables.

`uv run simile cafe barista` made her with N1's resident prompt and one Sonnet call. Her values are
the profile in N1's sampling pool farthest from everyone else's, and the prompt adds her job and
the flat above the shop, and allows only writing or no craft. It writes only her own file, and
refuses if someone already lives above the café. Her voice came from N2's `design_npcs.py` and
`speak_npcs.py`, and her doll from `simile dolls paint`.

## Shifts

- A barista who works at the café follows their E3 `shifts`. When B1 sends them to work, late,
  early or on time as their Discipline has it, the café takes them to the till, the entry of
  `coffee_shop_staff` behind the counter, and holds them there with B1's `hold`. They take orders
  once the shift has started. If they skip a day the café stays shut, and anyone who comes in sits
  down instead of queuing. Mirela works every day from 07:00 to 17:00.
- A barista who only lives there keeps the café's own hours, `opens` (07:00) to `closes` (17:00).
- At the till she makes no decisions and nobody seeks her out, and she's up whatever her wake time
  says. A talk with the player pauses the hold, and she goes back to the till afterwards.
- When her shift ends she takes no new customers, serves the queue, then is released to decide as
  anyone does.
- If something else lets go of her mid-shift, the café shuts until B1 sends her back: everyone
  coming, queuing or waiting is let go, and the order in hand is dropped. A customer someone else
  lets go of takes their order with them, so a drink is never made or charged for someone who's left.
- Only while she's on shift does the Daily Grind feed anyone: `Cafe.supply` wraps B1's `supply`
  hook, so off shift the coffee shop scores nothing for hunger and meets none, while E4's economy
  still says what the other shops and the fridges have.
- Off shift, whenever she's home, resting or asleep, she goes to `upstairs`, the foot of the stairs
  behind the counter, rather than standing at the café's entry, which is the front of the queue.
  B1's stay carries on there. Asleep in her bed, she's left there until she wakes.

## Where things are

`entrance`, `machine`, `hand_over`, `pickup`, `upstairs` and `seats` are a `Layout` in
`CafeConfig.layouts`, by the map the café's location is on: `coffee_shop_floor_0`
(`content/street/`), where the counter, the queue and the bar are downstairs, `upstairs` is the foot
of the stairs at the east end, and the tables are on the floor above. The barista sleeps in her bed
in the flat on the top floor.

## The queue

- A resident who chooses the coffee shop while it's open, and hasn't been served in the last `again`
  (90) minutes, is a customer. They head for `entrance`, inside the door. Once they're inside, on
  any of the café's floors, they join the queue: the front is the counter's `stand` (also
  `coffee_shop_queue`'s entry), and the rest line up behind it along the floor through the lane,
  east. Someone already inside who chooses it, on
  any floor, joins at once. A resident whose goal was the coffee shop before the café took any
  notice, like a saved one standing on the terrace, is left alone until they next decide.
- The barista serves the front of the queue, one order at a time: once she's at the till and they're
  on their spot, they talk, then the customer moves to `pickup` at the end of the counter and the
  next one steps up. She makes the drink at `machine` for its `seconds` from the menu, then hands it
  over at `hand_over`.
- Someone who has queued for `patience` (10 minutes) without being served gives up and leaves, and
  someone whose walk in ends short of the café is let go to decide again.
- Served, a customer sits down at a free seat beside a table for `stay` (10 to 30 minutes), or leaves
  and decides again. The chance of sitting is `sit` plus Connection, Pleasure and Peace of Mind, less
  Ambition.
- Anyone else who comes to the café, writing there or back within `again`, sits at a table for B1's
  usual stay. Customers are held while they queue, order, wait and walk to a seat, and are released
  once seated, so others can seek them out.
- While they queue, order and wait, customers are in B1's `leave_player_alone`, and so is the barista
  on shift, so B5 doesn't have them greet the player. The player can still talk to any of them.
- Someone whose goal is already the café when it first sees them, as after loading a save, sits down
  for what's left of their stay rather than queuing again.

## Orders

**The menu** is `content/cafe/menu.json`: espresso, flat white, long black, chai and hot chocolate,
each with how long it takes and the values of who drinks it. A resident's usual is the drink their
values lean to, and they order it `usual` (75%) of the time, otherwise any drink, weighted to taste.

**Stock orders.** Most residents' orders are stock lines from `content/cafe/lines.json`, with no LLM
call: the barista greets them, they order and she confirms, or, once she knows them (familiarity
`regular`), she offers their usual. Then she calls the drink out and they thank her, or remark on the
wait if it was slow. These lines are published as `LineSpoken` with no conversation around them, so
the client shows and logs them but they're not voiced, and B3 doesn't reflect on them.

**Written orders.** An order is written by the LLM only when the ambient director would want a
conversation near the player anyway: the player is connected, not talking, within its `earshot` of
the barista or the customer, nothing has been in earshot for its `quiet` minute, it hasn't nudged
for its `retry`, and both would accept each other (B2's `accept_score`). Then one L1 `structured()`
call (Haiku 4.5, `purpose="cafe-exchange"`) writes two to five lines between them, the drink and
whether it's on the menu, from both sides' personas, how they feel about each other and the
customer's usual. It's played as a real conversation: `ConversationStarted`, a line drafted ahead
of each spoken, waiting for its audio, then `ConversationEnded`, so it's voiced and overheard, and
B3 reflects on it. If the call fails, it falls back to stock lines.

**Mistakes.** One time in `mistake` (6%) she makes the wrong drink. The customer says so, she
apologises and makes it again.

## The player orders

Standing on the counter's `stand` tile, the player is greeted by the barista as soon as she's free:
a stock line through B5's `interject`, so it's a B5 conversation like any other. Each line the player
says to her there goes through `Cafe.write`, B5's writer for her: one L1 `structured()` call (Haiku
4.5, `purpose="cafe-order"`, at B5's priority) returns what she says and, once they've asked for one,
the drink she'll make and its menu id, or none for something improvised. What she says is spoken
and voiced as B5 speaks any reply. The drink comes after its menu `seconds`, or
`improvised_seconds` (90), and she hands it over with a stock line in the same conversation. If the
player has walked off, she calls it out instead, outside any conversation. Everything else the
player says to her, away from the counter or once they've ordered, gets B5's usual reply.

## What orders change

Each order a resident is served becomes InteractionEvents, applied in code as B3 applies a
conversation's (R1's `apply_events` on R2's relationships, at `as_of` now) and stored with them:

| Event | Actor → target | Aspect | Valence, magnitude |
|---|---|---|---|
| made my drink | barista → customer | like | `served` (0.5, 0.15) |
| came in for a drink | customer → barista | like | `serving` (0.3, 0.1) |
| kept me waiting, if the wait from joining the queue was over `slow` (5 minutes) | barista → customer | like | `waited` (−0.4, 0.15) |
| got my order wrong | barista → customer | respect | `wrong` (−0.5, 0.2) |
| kept me waiting so long I gave up | barista → customer | like | `gave_up` (−0.6, 0.25) |

So familiarity grows with every order, and the barista's relationships with her regulars grow from
serving them. The customer also keeps an observation memory of each order, more salient when it
went wrong or slowly, and the barista one of each mistake. A written order's chat is B3's to reflect
on, as for any conversation. The player's orders are B5 conversations, so B3 reflects on them too.

`Ordered`, `Served` and `GaveUp` are published on the bus, so `simile headless` logs them.

Every constant is in `CafeConfig`.
