# Salvage Rights: game design

Where Simile goes after the POC. The [POC plan](poc-plan.md) builds a village of NPCs with values,
relationships and memories who talk to each other and to the player. This doc is the game built on
top of that: a dungeon crawler with character advancement in the spirit of Shadowrun, where the
village is the thing you're slowly giving up to get stronger.

It's a direction, not a spec. Nothing here is a task yet.

## The pitch

Someone you care about has disappeared, and you're trying to track them down. You can't afford to
look, so you sell what you have: your body. Under the village, in abandoned metro tunnels, back-alley
clinics buy healthy organs and fit cheap bionic replacements. Each part makes you more capable and a
little less human, and the village notices.

## The world

- **The village.** Warm, comparable to current day or near future tech level, ordinary people. These are Simile's NPCs: each has core values,
  relationships and memories, and they gossip. It should feel like the cleantidy village we already have.
- **The city.** Tall glass towers visible on the horizon from the village, built on biotech money. Apex Biotech grows and sells replacement
  organs that keep the rich young. It's legal, respected, and has saved lives in the village too.
- **The tunnels.** Where the poor live, and where the dungeon is. Clinics, salvage, scrap markets, and the bodies of everyone who went down before you. Deeper levels are older, stranger and more dangerous.

## The hook is optional

The search is the story's spine, but nothing forces the player to follow it. A player can ignore it
and just go delving. So the tunnels have to be fun on their own, with the search as the reason to go
deeper for players who want one.

## The core loop

1. Go down into the tunnels.
2. Bring back salvage, money and clues.
3. Spend it on bionics and skills.
4. Come back up changed, and see how the village reacts.
5. Use what you've become to get somewhere you couldn't before.

## The central tension

**Every upgrade opens one kind of door and closes another.**

- An eye that reads wiring let's you open maintenance hatches, but some people in the village get nervous around you.
- An implant that reads emotions talks you past certain NPCs, but some people sense they're being read and start to be pretty cagey around you
- A stomach that runs on a power cell means you never need to eat, but you never share a meal again or bond with people that way

Physical access goes up and social access goes down. Most of what you need to know is held by
people, so every upgrade is a real decision. This is Shadowrun's Essence idea, expressed through the
relationship model rather than a stat: NPCs' like, trust and respect for you shift with what you've
become, weighted by their values. Tradition and Security distrust it; Ambition and Adventure admire
it or are curious about it.

## Characters and advancement

Shadowrun-style: no locked classes. You become an archetype by what you install and what you train.

### Archetypes

Starting points, not restrictions. A character can mix them, at the cost of being less human.

| Archetype | Built from | Opens |
|---|---|---|
| Muscle | Hydraulic limbs, dermal plating, reflex boosters | Forced doors, heavy salvage, surviving the deep levels |
| Hacker | Datajack, cranial deck | Terminals, cameras, digital locks, corporate data |
| Face | Emotion-reading optics, voice modulator | Talking past guards, reading what NPCs won't say |
| Tracker | Thermal and low-light eyes, enhanced hearing | Following trails, finding hidden routes, spotting traps |
| Rigger | Control rig, drones | Scouting ahead, reaching places a body can't |

The Face is a bit of a contradiction: the parts that make you better at people also make people trust you
less.

### Two kinds of advancement

- **Body: bionics.** Bought with money, fitted at a clinic. May require certain key ingredients that need to be found/acquired in the game world. Each one replaces something human and gives an ability. Bionics are the main way the world opens up. 
- **Mind: skills.** Improved by use and by spending what you earn from runs (Shadowrun's karma). Hacking, climbing, haggling, first aid, tunnel lore. Many skills need a bionic to use: you can know how to deck, but not without a datajack. 

The split matters because of death (below): **the mind comes back, the body doesn't.**

### Humanity

How much of you is still you. It isn't a gauge the player watches; it shows up in how people treat
you. It feeds the relationship model, unlocks and closes conversation options, and decides how the
ending plays out.

## Money

Selling an organ only gets you started: enough for a first cheap part or a few days of help. Real
money comes from the tunnels: salvaged tech, things worth selling on the surface, bounties, and what
other delvers left behind when they died. This keeps the organ trade as the desperate first step
instead of an economy the player can farm.

## Death

Death is permanent for the body and not for you.

- **You wake up again** in your house in the village, in a whole, organic body with no bionics. The
  world has carried on, and you keep your skills and memories.
- **Your corpse stays where you died,** with every bionic and item on it. Getting back to it, and
  cutting your old parts out of your own body, is the run.
- **Your house is your stash.** Whatever you left there on purpose is waiting: money, gear, a spare
  part. Over time it can hold more, and eventually expensive equipment.
- **Companions don't come back.** Anyone you recruit dies for good, and their bodies and loot stay
  too. You can go back for them, and the village remembers who you got killed.

Why you come back is a mystery the story answers late (see below).

Deliberately left out: a social cost for coming back. Losing your bionics is punishment enough.

## The story

### Backstory

Dr Aris is eighty-four and holds the village together. She treated your childhood fevers, patched up
everyone's machines and kept the village running on cast-off Apex supplies for decades. Everyone owes
her something. One morning her door is open, her tea cold, her kit left behind. The village assumes
she wandered off to die.

You don't believe it. Tracking her takes money you don't have, so you go down into the tunnels and
sell your first organ.

The search goes on for months, and each step costs another part of you. Back in the village, people
start to step back when your joints hiss. Eventually your eyes pick up a biometric trail in Apex's
security logs and follow it down deep into the sewers and then back up again into the spires of the Apex glass towers.

### The game ending

When you eventually track down what happened to hew, she's sitting in a penthouse, drinking tea, young again. And she's wearing your parts: your eyes look
back at you, your hand holds the cup, she speaks with your voice. Whatever you sold, she has.

Why she left and how she got your parts remains a mystery for the player to speculate on.

The game ends when you find her.

## Design rules

- **Facts live in the simulation; the LLM only voices them.** Who did what, who owes whom, what
  things cost and where the trail leads are deterministic state. That's what makes the game balanced,
  testable and winnable.
- **No talking your way to a win.** The LLM turns what the player says into bounded effects on
  relationship scores. NPCs act on those scores, not on whatever the player types.
- **The tunnels are where you get the means; the village is where the game happens.** If the tunnels
  stop needing the village, the dungeon has become a separate game and Simile's core is wasted. There are key items we need for upgrades that can only be obtained in the village... and key pieces of information for the quest that can only be obtained from people in the village or the Apex towers.

## Build order

Each stage should be fun before the next starts.

1. **The loop.** One village, one tunnel level, one clinic, three or four bionics, and one missing
   person. Go down, come back changed, the village reacts. No combat, no companions, no stash.
   Danger comes from hazards and being seen, not fights.
2. **Death.** Combat, death, waking at home.
3. **Salvage.** The house stash, corpses that stay, salvaging your own body
4. **Companion.** One recruitable companion whose values decide how far they'll follow you
3. **Depth.** More tunnel levels, puzzles, skills, the full archetype spread.
4. **The city and the ending.** Apex, the trail into the spires, Dr Aris and the endings.

Left for later, if the game still needs them: combat beyond the basics.

## Open questions

- What does danger look like in the tunnels before there's combat? This could come from the platform nature of the game... getting crushed by trains in the metro, getting sucked into sewer pipes etc. Those are situations where you wouldn't be able to recover your corpse so you reall don't want to die that way.
- How fast should humanity loss show up in NPC reactions, and can it ever be won back short of dying? I think we have to experiment with this to find the right rate.
- Does the village population change over a long game (people move, die, go missing too)? We could have a new person join the village every now and then but if you take them all into the dungeons and get them killed, ultimately the village population starts to look a bit sparse. 
- How much of the map is generated each game, and how much is authored around Dr Aris's trail? I'd favour a roguelike where most of it is fresh/generated but there are some things that every may must have (to support the core game story). 
