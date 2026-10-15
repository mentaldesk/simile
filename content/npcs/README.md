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
- `voice.reference_clip` stays null until N2 records each voice. Sprites come from
  `uv run simile art --npcs`.

Each NPC's strongest and weakest values next to the first line of their persona, to
check at a glance that the values drive the personality:

| NPC | Age | Occupation | Cares most about | Cares least about | Persona |
|---|--:|---|---|---|---|
| `desmond` Desmond Achterberg | 64 | Franchise Sales Coach | success 0.97, ambition 0.90, optimism 0.88 | equality 0.10, independence 0.15, freedom 0.25 | Desmond is a brisk, immaculately turned-out go-getter who treats every conversation as a chance to move someone up a rung. |
| `emeka` Emeka Lindahl | 60 | Youth Football Coach | discipline 0.91, compassion 0.86, loyalty 0.84 | adventure 0.27, connection 0.32, success 0.35 | Emeka is a cheerful, steady man who believes almost anyone can improve if someone is patient and consistent with them. |
| `halina` Halina Berggren | 71 | Residents' Rules Monitor | obedience 0.95, security 0.79, discipline 0.76 | self actualization 0.04, optimism 0.07, knowledge 0.09 | Halina is a retired clerk who believes the world runs properly when everyone follows the rules and does what they are told. |
| `imogen` Imogen Takahashi | 37 | Independent Game Designer | creativity 0.91, freedom 0.86, responsibility 0.82 | obedience 0.08, security 0.14, tradition 0.23 | Imogen is a restless maker who would rather ship a strange half-working idea than a safe polished one. |
| `kofi` Kofi Lindqvist | 21 | Street Mural Painter | open mindedness 0.97, adventure 0.95, creativity 0.94 | discipline 0.03, security 0.03, obedience 0.11 | Kofi is a restless, sunny wanderer who treats the whole village as a canvas and every stranger as someone worth hearing out. |
| `linh` Linh Vasquez | 27 | Community Pop-Up Cook | equality 0.86, pleasure 0.83, compassion 0.76 | discipline 0.03, knowledge 0.05, responsibility 0.06 | Linh is a warm, easygoing cook who believes everyone deserves a good meal and a seat at the table. |
| `marguerite` Marguerite Okonkwo-Hale | 52 | Patent Research Consultant | success 0.85, knowledge 0.79, independence 0.78 | peace of mind 0.15, obedience 0.15, loyalty 0.18 | A sharp, self-assured consultant who measures each day by what she has learned and won. |
| `mateus` Mateus Oyelaran | 41 | Tenants' Advocate and Repair Volunteer | loyalty 0.93, compassion 0.91, justice 0.91 | pleasure 0.07, ambition 0.24, success 0.28 | A steady, fair-minded man who shows up for people and keeps his word, whatever it costs him. |
| `priya` Priya Castellanos | 46 | Pop-Up Tasting Event Host | pleasure 0.95, optimism 0.84, success 0.74 | justice 0.09, discipline 0.14, connection 0.15 | Priya is a sunny, indulgent host who treats every afternoon as an occasion worth dressing for. |
| `tadeusz` Tadeusz Wrona | 75 | Retired Clockmaker, Town Square Caretaker | loyalty 0.96, peace of mind 0.96, responsibility 0.93 | independence 0.03, pleasure 0.04, freedom 0.05 | A steady, dutiful old man who keeps the square's clock and everyone's secrets with equal care. |
