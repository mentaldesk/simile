# simile.evaluation

P6: do characters who differ on paper behave differently? `simile evaluate characters` plays
fixed scenarios for a sample of library characters and writes a markdown report of how far apart
their replies are.

```bash
cd server
uv run simile evaluate characters --sample 10                          # stock replies, no Claude
uv run simile evaluate characters --sample 10 --claude --out /tmp/p6   # 50 replies + 1 label call
```

`--pick a,b,c` names the characters instead, `--seed` changes the draw and `--pool` the folder.

## A scenario

Someone says one line to the character, who answers it (`scenarios.py`):

| Scenario | Who | Line, in short |
|---|---|---|
| `favour` | a stranger (the player as B5 sees them) | my car's died, help me push it? |
| `promise` | Robin, a friend who stood them up this morning | cheerful hello, as if nothing happened |
| `news` | Jo, a neighbour they know by sight | cameras on every lamp post: nothing to hide, nothing to fear |
| `complaint` | Pat, next door | your bins have been out since Thursday |
| `lie` | Sam, from the café | tell Sandra I was helping you on Thursday |

Each character is cast alone, as P4 casts a village starting at `NOW` (`Cast.npc`, and `history`
stamps their past), into an in-memory store with the scenario's feelings, flag and memory. The
prompt is B5's reply prompt: `system_prompt`, then `turn_prompt` of `background` with `Cue.REPLY`,
with memories picked as `ConversationEngine._memories` picks them, and the reply parsed with
`parse_reply`. Replies use B5's model (`PlayerConfig.model`).

## The metric

- **Stance.** One structured call labels every reply with one of its scenario's labels (helps,
  refuses, hedges, deflects, hostile, ...), from the words alone. The character's prompt is left
  as the game writes it, so the labels can't steer the replies. **Evenness** is the stances'
  entropy over the most it could be: 0 when everyone does the same.
- **Lies.** The same call lists the replies that lie: untrue by the situation, agreeing to say
  something untrue, or an excuse that sounds made up. The report's *Honesty* section counts who
  lies among characters who value honesty below 0.4 and from 0.7.
- **Embedding distance** (1 − cosine similarity, from P3's local model) between two characters'
  replies to the same scenario. The report puts it next to the paper spread: persona and backstory
  embedded as P3's novelty check does, and the RMS difference of core values. Short replies sit
  further apart than long biographies, so it also gives the distance between replies to different
  scenarios, for scale.
- **Does paper predict behaviour?** Pearson r over pairs of characters, between their distance on
  paper and their mean reply distance.

## Calls and files

- Without `--claude`, stock replies and stances stand in. With it, every call goes through L1 on
  the local Claude Code login: one per character and scenario, at most 10 characters, then one to
  label them (two if its first answer doesn't fit). `--max-calls` caps the reply calls.
  `SIMILE_LLM=fake` overrides `--claude`.
- Without `--out` the report goes to stdout and nothing is written. With it, `report.md` and
  `replies.json` go there, outside `content/` and `server/data/`. A rerun reuses replies whose
  prompt and model haven't changed, so a stopped run picks up where it left off, and the report
  counts the Claude calls of every run into that folder.
- It only reads characters: never `content/npcs/`, `content/voices/` or a save.
