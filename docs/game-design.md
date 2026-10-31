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

- **The village.** Warm, ordinary people, at about today's tech level or a little beyond. These are
  Simile's NPCs: each has core values, relationships and memories, and they gossip. It should feel
  like the clean, tidy village we already have.
- **The maker space.** Aris's workshop at the edge of the village, standing empty since she
  disappeared. Its machines are broken, but bringing them back to life gives you a bionics bench in
  the village (see below).
- **The city.** Tall glass towers on the horizon, visible from the village, built on biotech money.
  Apex Biotech grows and sells replacement organs that keep the rich young. It's legal, respected,
  and has saved lives in the village too.
- **The tunnels.** Where the poor live, and where the dungeon is. Clinics, salvage, scrap markets,
  and the bodies of everyone who went down before you. Deeper levels are older, stranger and more
  dangerous.

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

## Seeing what you can't reach yet

Like Ori and Dead Cells, the tunnels show you places before you can get to them: a ledge too high to
jump to, a door with no handle, a terminal with no way to plug in. You don't know what's behind
them yet, only that something is. Each bionic you install turns some of those into routes, so the
map you've already walked keeps opening up. Hard-to-reach corners hold secrets, such as cash, parts
or a clue, for players who look.

## The central tension

**Every upgrade opens one kind of door and closes another.**

For example, maybe:
- An eye that reads wiring lets you open maintenance hatches, but some people in the village get
  nervous around you.
- An implant that reads emotions talks you past certain NPCs, but some people sense they're being
  read and get cagey around you.
- A stomach that runs on a power cell means you never need to eat, but you never share a meal again
  or bond with people that way.

These don't have to be the implants you can get in the game... they're just ideas. Ideally we should
design/imagine the implants around problems that we create in the game, which the implants can help
you solve (or are necessary for you to be able to solve). 

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

### Two kinds of advancement

- **Body: bionics.** Each is fitted at a clinic for money and the parts its recipe lists, found
  in the world or bought. Each one replaces something human and gives an ability. Bionics are the
  main way the world opens up. A **power cell** in place of the stomach comes first: it runs every
  other bionic, and a bigger cell runs more of them.
- **Mind: skills and recipes.** Skills improve by use and by spending what you earn from runs
  (Shadowrun's karma): hacking, climbing, haggling, first aid, tunnel lore. Many skills need a
  bionic to use: you can know how to deck, but not without a datajack. Recipes are what you know
  about building bionics, found on Aris's benches, in terminals and in the tunnels. The clinic
  only fits what you have a recipe for, so nobody shows you a menu of everything you could become.

The split matters because of death (below): **the mind comes back, the body doesn't.**

### Humanity

How much of you is still you. It isn't a gauge the player watches; it shows up in how people treat
you. It feeds the relationship model, unlocks and closes conversation options, and decides what you
see when you find Aris.

## Money

Selling an organ only gets you started: enough for a first cheap part or a few days of help. Real
money comes from the tunnels: salvaged tech, things worth selling on the surface, bounties, and what
other delvers left behind when they died. This keeps the organ trade as the desperate first step
instead of an economy the player can farm.

Parts can be sold too, for anyone who'd rather have the money. The trader sells back what you sold,
at twice the price. The clinic buys each recipe once, for a one-off sum, and you still know it.

## The maker space

Aris's workshop is yours to bring back, one machine at a time. Some of the earliest quests are just
finding the money and parts to repair them. Each working machine lets you do more with bionics
without a back-alley clinic: tune/modify the implants you have, strip salvage for parts, and eventually build
your own. Her notes and half-finished work are still on the benches, and some of them are clues.
By gaining access to some of her archives you can get access to more advanced designs. 

## Dangers

Before you have weapons, the tunnels are about getting past things, in the spirit of Rick
Dangerous: each danger moves in its own way, and learning how is the puzzle. Getting hurt costs
health, and at none you collapse and wake at home, as when you starve. Each danger is also a door:
the bionic or tool that answers it is further on.

- **Rats** are the weakest. Jumping on one kills it. Running into a handful hurts enough to matter.
- **Recycler bots** are broken maintenance robots, in the sewers and on the metro's floor. They
  collect the same salvage you do, and ignore you while you're wholly human. Once you're fitted,
  they try to recycle you. They can't climb ladders or stairs, so height is the way past them. Later
  you can destroy one and take everything it collected.
- **Wild dogs** are few and frightening. They're faster than you, even on your first bionic legs,
  and the only way out is up a ladder or through a door. Without the legs or a weapon, their den
  is almost certain death. Matching their speed takes a long time.
- **Bats** roost in the dark and attack only while your lamp is on. Some caves are too thick with
  them to cross by lamplight, until the infrared eye lets you see without it. Sonar might drive
  them off, later.
- **Snakes** hide in knee-high water, which slows you down. Ripples show where they are.
- **Organ cultures** are Apex's failed grow-vat organs, dumped in the sewers. They creep in the
  dark and shrink from light, so the lamp is a tool that costs battery.
- **Radioactive waste** leaks from medical isotope drums. Being near them builds a dose, an
  ailment that fades slowly. With one kidney it fades more slowly still.

Some ailments fade on their own and some, like an infected bite, last until they're treated.

Getting hurt has to be felt: a sound, a flash and a flinch every time, so the player knows what hit
them.

Later the maker space prints and builds weapons: a plastic pistol that lasts a few shots, charges
that open walls, and maybe a sonar for the bats.

## Death

Death is permanent for the body and not for you.

- **You wake up again** in your house in the village, in a whole, organic body with no bionics. The
  world has carried on, and you keep your skills and memories.
- **Your corpse stays where you died,** with every bionic and item on it. Getting back to it, and
  cutting your old parts out of your own body, is the run.
- **Your house is your stash.** Whatever you left there on purpose is waiting: money, gear, a spare
  part. Over time you can fit it out so that it can hold more.
- **Companions don't come back.** Anyone you recruit dies for good, and their bodies and loot stay
  too. You can go back for them, and the village remembers who you got killed.

Why you come back is never explained. Like the ending, it's for the player to wonder about.

## The story

### Backstory

Aris runs the maker space. If it's broken, she can fix it: the pump that keeps the village's water
running, the bakery's oven, half the phones in town. People bring her their broken things because
nobody else can fix them, and they take them away again quickly.

She's more machine than woman, and she made most of the machine herself. Nobody knows quite how
much: a steel hand, an eye that glows faintly in the dark, a voice that comes through a grille in
her throat. The village has an unspoken rule that whatever she does to herself in that workshop at
night is best not asked about. Parents steer their children away from her door.

You were one of the children who didn't stay away. She let you hang around the workshop, taught you
to solder and told you what everything was for. She's the closest thing you have to family.

Then comes the incident. One night the maker space is smashed up and she's attacked in the lane 
behind it. She survives, but one of her mechanical hands is torn half off, and she won't say who 
did it. A week later the workshop door is standing open, her tea cold, her tools left on the bench.

The village shrugs. Some are relieved, a few say "good riddance" out loud, and nobody official comes
asking.

You don't believe she left on her own. Someone in the village knows what happened that night, so
that's where the search starts. But the trail leads underground, following it takes money you don't
have, and the clinics in the tunnels pay well for healthy organs.

The search goes on for months, and each step costs another part of you. In one tunnel clinic, the
bionics for sale include a steel hand and a faintly glowing eye. You'd know her work anywhere. You
may end up wearing them. Back in the village, people start treating you the way they treated her.
Eventually the trail leades you to Apex's security logs... but you can't just walk in through the
front door. Delving further you discover there are abandonned maintenance shafts into the Apex 
towers in the sewer system... so you follow the trail, deep into the sewers and then eventually 
back up into the spires of the Apex towers and past the internal security systems. 

### What the backstory gives the game

- **You live her life.** The villagers who disliked her react to your bionics the same way. The
  simulation does that for free: Tradition and Security already distrust bionics.
- **The search starts in the village.** The first leads come from questioning people, not from the
  tunnels.
- **The suspects come from the simulation.** The failed repair and the attack are facts in the sim's
  state, and who was hurt and who attacked her are generated each game from the villagers whose
  values and grievances make them hostile to her. The attackers are a red herring: they hurt her,
  but they aren't why she disappeared.
- **Her maker's mark is a trail.** Every part Aris built carries her mark. Her own parts turn up for
  sale in the tunnels, and other people's bionics carry the same mark, which raises the question of
  who she was building for.
- **She taught you not to fear machines.** That's why you're the kind of person who lets a back-alley
  mechanic cut you open.

### The ending

When you finally track her down, she's sitting in a penthouse, drinking tea, young again and wholly
human. And she's wearing your parts: your eyes look back at you, your hand holds the cup, she speaks
with your voice. Whatever you sold, she has. The engineer who built herself out of metal has had
herself made back into flesh - your flesh.

The game ends there. Why she left, how she got your parts and what happens next are left for the
player to speculate about.

## Design rules

- **Facts live in the simulation; the LLM only voices them.** Who did what, who owes whom, what
  things cost and where the trail leads are deterministic state. That's what makes the game balanced,
  testable and winnable.
- **No talking your way to a win.** The LLM turns what the player says into bounded effects on
  relationship scores. NPCs act on those scores, not on whatever the player types.
- **Every danger has a solution.** As in Rick Dangerous and the early platformers, each map is a
  puzzle: an enemy you can't kill moves in a pattern you can learn and time your way past, or there's
  a route it can't follow (a ladder, a ledge, a door), or a way to kill it. Walking through and
  taking the damage is never the only way. Every danger placed on a map comes with its solution,
  checked by a test.
- **Light is scarce.** The lamp's battery is a resource to ration and plan around. Dark stretches
  are long enough, and plugs far enough apart, that reaching the next one is a relief.
- **The tunnels are where you get the means; the village is where the game happens.** If the tunnels
  stop needing the village, the dungeon has become a separate game and Simile's core is wasted. Some
  components that upgrades need can only be had in the village, and key pieces of information for the
  search can only come from people in the village or the Apex towers.

## Build order

Each stage should be fun before the next starts.

1. **The loop.** One village, one tunnel level, one clinic, three or four bionics, and one missing
   person. Go down, come back changed, the village reacts. No combat, no companions, no stash.
2. **Parts, power and dangers.** Recipes and parts, the power cell, health, kicking, and the first
   dangers to get past. Collapsing still wakes you at home; nothing stays where you fell but what
   you carried.
3. **Salvage.** The house stash, corpses that stay, salvaging your own body, and the maker space's
   first machines.
4. **Companion.** One recruitable companion whose values decide how far they'll follow you.
5. **Depth.** More tunnel levels, puzzles, skills, the full archetype spread.
6. **The city and the ending.** Apex, the trail into the spires, discovering Aris was a patient of
    Apex, getting her current address and eventually finding her in an apartment in the city.

## Open questions

- **How fast should humanity loss show up in NPC reactions?** This needs experimenting to find the right rate.
- **Does the village population change over a long game?** A new person could join the village now
  and then (up to a certain maximum), but if you take them all into the tunnels and get them killed, the 
  population can get sparse and take a while to grow back... so no hard minimum (except that obviously some
  of the NPCs won't want to join you as a companion - so they're presumably safe). 
- **How much of the map is generated each game, and how much is authored around Aris's trail?**
  Probably a roguelike: most of it fresh each game, with a few things every map must have to support
  the story.
