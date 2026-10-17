# NPCs

The village's residents. Each `<id>.json` is an F2 `Npc`, generated from `server/` by

```bash
uv run simile generate-npcs --count 10 --seed 0
```

Don't edit them by hand: rerun the command, which replaces them all.

- **Values** are sampled in code, so the seed always gives the same ones: correlated
  through four latent traits, then spread across value space by farthest-point sampling
  (`server/simile/npc/values.py`). Age, gender and home are fixed in code too.
- **Everything else** is written by Claude, one Sonnet call per NPC, from those values,
  so a rerun gives new names and stories.
- **Crafts**, what each resident makes in their own time, can be chosen again without
  changing anything else with `uv run simile npc crafts`, one Sonnet call per NPC.
- `voice.reference_clip` stays null until N2 records each voice. Sprites come from
  `uv run simile art --npcs`.

Each NPC's strongest and weakest values next to their craft and the first line of their
persona, to check at a glance that the values drive the personality:

| NPC | Age | Occupation | Craft | Cares most about | Cares least about | Persona |
|---|--:|---|---|---|---|---|
| `desmond` Desmond Puna | 41 | Tenants' Rights Caseworker | writing: plain tenants' rights guides and stories | loyalty 0.93, compassion 0.91, justice 0.91 | pleasure 0.07, ambition 0.24, success 0.28 | Desmond is a rumpled, steady man who will drop his own plans to sit with someone in trouble and see their problem through to the end. |
| `henrietta` Henrietta Okonkwo-Bell | 71 | Residents' Association Secretary | writing: numbered rules and reminders for residents | obedience 0.95, security 0.79, discipline 0.76 | self actualization 0.04, optimism 0.07, knowledge 0.09 | Henrietta is a stern, orderly woman who believes most trouble comes from people not following the rules they were given. |
| `ingrid` Ingrid Salazar-Holm | 37 | Experimental Textile Designer | mural: bold abstract murals from fabric-waste patterns | creativity 0.91, freedom 0.86, responsibility 0.82 | obedience 0.08, security 0.14, tradition 0.23 | Ingrid is a restless maker who treats every free hour as a chance to build something nobody has seen before. |
| `kofi` Kofi Lindqvist-Mensah | 21 | Street Mural Artist | mural: half-finished murals inviting passers-by to add | open mindedness 0.97, adventure 0.95, creativity 0.94 | discipline 0.03, security 0.03, obedience 0.11 | Kofi is a restless, generous young painter who says yes to almost any odd idea and will happily argue the other side just to see it from there. |
| `lachlan` Lachlan Brennan-Singh | 60 | Youth Football Coach | writing: short pep talks for young players | discipline 0.91, compassion 0.86, loyalty 0.84 | adventure 0.27, connection 0.32, success 0.35 | Lachlan is a cheerful, steady coach who believes anyone can get better if they turn up and put in the work. |
| `marguerite` Marguerite Oyelaran | 52 | Patent Strategy Consultant | writing: blunt valuation notes on local inventions | success 0.85, knowledge 0.79, independence 0.78 | peace of mind 0.15, obedience 0.15, loyalty 0.18 | A sharp, self-made patent strategist who is always working out what an idea is worth. |
| `odalys` Odalys Ferreira-Nakamura | 27 | Community Pop-up Kitchen Host | mural: painted napkin-doodle menus for shared tables | equality 0.86, pleasure 0.83, compassion 0.76 | discipline 0.03, knowledge 0.05, responsibility 0.06 | Odalys is a warm, easygoing woman who wants everyone fed, included and having a good time, and she will quietly move a seat so the person at the edge ends up in the middle. |
| `priya` Priya Vandenberghe | 46 | Pop-up Cocktail Bar Owner | writing: glowing cocktail menu blurbs for imaginary bars | pleasure 0.95, optimism 0.84, success 0.74 | justice 0.09, discipline 0.14, connection 0.15 | Priya is a glossy, sunny hustler who turns every evening into an occasion and every setback into a story for later. |
| `raymond` Raymond Tay | 64 | Franchise Development Broker | writing: motivational quarterly targets and sales-floor maxims | success 0.97, ambition 0.90, optimism 0.88 | equality 0.10, independence 0.15, freedom 0.25 | Raymond is a sharp-suited, relentlessly upbeat deal-maker who is sure the next quarter will be the best yet. |
| `tobias` Tobias Fallon | 75 | Retired Ferry Lockkeeper | writing: daily river-level log entries and hymn-like notes | loyalty 0.96, peace of mind 0.96, responsibility 0.93 | independence 0.03, pleasure 0.04, freedom 0.05 | Tobias is a steady, dutiful old man who keeps his word, his routines and his neighbours' trust. |
