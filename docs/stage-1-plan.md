# Stage 1 plan: the loop

Stage 1 of [Salvage Rights](game-design.md#build-order), the game built on the [POC](poc-plan.md):

> One village, one tunnel level, one clinic, three or four bionics, and one missing person. Go down,
> come back changed, the village reacts. No combat, no companions, no stash.

Each task is one issue and one PR. All of them are sub-issues of a new stage 1 tracking issue, and
dependencies are GitHub "blocked by" links, as in the POC.

## Decisions

The user's answers to the open design questions.

| Decision | Choice |
|---|---|
| **Where** | The village, as it is now. One level down, an **abandoned metro station**, designed by hand, with the clinic in it. Below that, the **sewers**, generated each game in the spirit of WazHack, and reached by a maintenance lift from the clinic. |
| **Look** | The village stays clean, as today's papercraft until its re-render. The metro, the clinic and the sewers use the grimy cartoon from #329's study. |
| **Tension, before combat** | **Darkness and hunger.** Parts of the tunnels are unlit, and you need a lamp to see. Get lost in the dark and you can starve. |
| **Gating and secrets** | The tunnels show you places you can't reach yet (see [*Seeing what you can't reach yet*](game-design.md#seeing-what-you-cant-reach-yet)). Hard-to-reach corners hold secrets: extra cash or items. |
| **The bionics** | 1. **Hydraulic legs:** reach higher ledges.<br>2. **A datajack, in exchange for a vertebra:** interface with basic machines, including the maintenance lift from the clinic down to the sewers.<br>3. **An infrared eye:** see a facial flush when someone may be lying. It costs the most socially. |
| **What upgrades close** | The villagers, at first. Some talk to you less once you're visibly bionic. What they can see of you goes into every conversation, and each resident has their own tolerance for cyborgs, from their values. Some react strongly against, others barely mind. |
| **Aris's attackers** | **Generated each run.** One, two or three residents, with a credible reason that changes each run, written into each attacker's memories. |
| **Who voices a lie** | Lies are decided in code (#285), so the infrared eye can read them exactly. Whether a local model should voice the suspects, now that voices are off and speed matters less, is tested in S14. Claude stays the default until then. |
| **Maps** | The metro and clinic are authored. The sewers are generated, seeded per game. |

## Architecture additions

- **The player becomes stateful:** money, what they carry, their body (organs and bionics), hunger,
  and a hidden humanity. It's saved with the world, like the residents' state.
- **Facts about the incident live in the sim** ("facts live in the simulation; the LLM only voices
  them"). They cover who attacked Aris, why, who saw what, and who knows what. Conversations read
  them, and the journal records what the player has learned.
- **Levels below the village** are maps like the village's streets and floors, reached by the metro
  stairway and the lift. Movement, jumping and ladders work as they do today.
- **Light** is a property of map areas. The client draws darkness, and the player's lamp makes a
  light radius around them.

## Tasks

### Contracts first, each its own small PR

| ID | Task | Done when |
|---|---|---|
| S1 | **Player state:** money, carried items (salvage, food, the lamp) with a carry limit, body slots (organs present or sold, bionics fitted), hunger, and humanity (hidden; derived from what's fitted). Saved with the world. A protocol message for the client's view of it. | Schema, protocol and generated types merged. Old saves load with a default player. |
| S2 | **Facts and clues:** a `Fact` (what happened, when and where, who it's about, who knows it, how willing each is to tell). The incident (attackers, motive, the night). A journal entry (what was learned, from whom, whether the eye saw them flush). | Schema and protocol merged, with example fixtures. |

### Then, in parallel where their paths allow

| ID | Track | Task | Depends on |
|---|---|---|---|
| S3 | World | **The metro, by hand:** a stairway down from the village, platforms, tunnels and the clinic, with dark stretches, places that are visible but locked (a high ledge, a dead terminal, the lift), and secrets. Painted in the grimy cartoon. | S1 |
| S4 | World, client | **Darkness and the lamp:** lit and unlit map areas, a light radius from the lamp, and places you've seen but can't currently see, drawn dimmed. | S3 |
| S5 | Behaviour | **The player gets hungry:** eat at home, at the café or noodle bar (paid), or from what you carry. Starving collapses you. Until stage 2 adds death, you wake at home, hungry, with what you carried left where you fell. | S1 |
| S6 | Economy | **Salvage:** things to pick up in the tunnels, a carry limit, and selling them at the clinic and a scrap trader, at prices from the economy. Folds in the part of #75 that stage 1 needs. | S1 |
| S7 | NPC, economy | **The clinic:** a tunnel doctor (not a villager) with values, a voice and a stall. Buys a kidney for your first money, and fits the three bionics for money and the part each replaces. Prices and stock are sim facts that the doctor only voices. | S1, S6 |
| S8 | World, client | **The bionics' abilities:**<br>- the legs raise the jump height<br>- the datajack lets you use machines (the lift, the dead terminal)<br>- the eye shows a flush on a speaker whose line is a lie, read from the code's lie decision. | S1, S3, S7 |
| S9 | World | **The sewers, generated:** one level per game, built from rooms, pipes, ladders and drops, with dark areas, salvage, secrets and one clue. Seeded, and checked to be reachable with the three bionics, but not without them. | S3, S4, S8 |
| S10 | Art | **The player, visibly bionic:** the player's painted figure in every combination of the three bionics, in every pose, painted as edits of their figure (#337's approach). Or overlays, if those hold up. Show both, and say which. | S1 |
| S11 | Social | **The village reacts:**<br>- what a resident can see of you starts every conversation prompt<br>- each resident gets a cyborg tolerance from their values (Tradition and Security against; Adventure, Ambition and Open-mindedness for), some strong<br>- seeing a new bionic is a relationship event weighted by that tolerance<br>- low tolerance makes a resident avoid you and decline to talk<br>- gossip spreads it through the existing memories. | S1 |
| S12 | Story | **Aris and the incident:**<br>- Aris as an absent character, with notes and clues in her empty workshop (the maker space)<br>- each run picks one to three attackers from the residents whose values and grievances fit, with a motive written once at world creation (Sonnet)<br>- the facts go into their memories, and witnesses saw parts of it<br>- residents tell what they know as trust allows<br>- attackers lie when asked, through #285's code-decided lies, which the eye reads. | S2 |
| S13 | Client | **The journal:** clues learned, from whom and when, with a mark where the eye caught a flush, and leads still open. | S2, S12 |
| S14 | LLM | **Who voices the suspects:**<br>- compare Haiku with directed lies against Gemma 4 through Ollama, for suspects and liars only, with #298's harness and tone check<br>- report how in character the lies are, the tone, and the speed with voices off<br>- recommend one. | S12 |

### Last

| ID | Task | Done when |
|---|---|---|
| S15 | **The loop, end to end:** a scripted playthrough runs in the sim and in a browser. It sells a kidney, buys the legs, reaches a secret, buys the datajack, takes the lift, finds the sewers' clue, comes back up, buys the eye, catches an attacker's lie, and sees residents react. | It passes in CI on the fake LLM. The user plays it. |

## Housekeeping when this starts

- Close the POC's tracking issue #1, with a final summary, and open the stage 1 tracking issue.
- Settle the held issues:
  - **Fold** #174 (maker space machines) into stage 3, which brings the machines back.
  - **Close** #105 (world interactions), which the game design supersedes.
  - **Keep** #90 (values drift) and #91 (memories drive behaviour) held. Humanity and gossip may want them later.
  - **#75 (prices and trades):** S6 and S7 take what stage 1 needs, and the rest stays held.
- The clean-cartoon town re-render stays deferred.

## Open questions

- **Starving before stage 2:** S5 has you collapse and wake at home, leaving what you carried where you fell. Is that right, or should starving wait for stage 2's death?
- **The lamp:** does its battery run down, adding another clock, or does it last forever?
- **What each bionic costs you:**
  - the legs replace your legs
  - the datajack takes a vertebra
  - the eye takes an eye
  - a kidney is the first thing you sell for money.

  Right?
- **The mismatched look:** the village stays papercraft while the tunnels are grimy cartoon, until the town's re-render. Fine for now?
