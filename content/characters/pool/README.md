# Character pool

Premade characters for the character library (#89). Each `<id>.json` is a `Character`,
generated from `server/` by

```bash
uv run simile characters generate --count 20 --seed 4
```

A rerun skips the characters already here, and the first characters of a seed's plan
are the same for any count, so a larger `--count` adds to the pool. Don't edit them by
hand: delete one and rerun to write it again, or rename one with
`uv run simile characters rename <id> "<new name>"`. `renames.json` records each
rename, so a rerun doesn't write the name the plan drew again.

This first pool has 20 characters, not the 30 #183 asks for: the user
asked for a small first pool. A larger one waits for #89's question on pool size.

- **Sampled in code** (`server/simile/characters/sheet.py`), from the tables in
  `content/characters/tables/`: the census skeleton, values spread across the pool,
  temperament, life events, a contradiction, wound, secret and want, mannerisms and the
  kinds of hook. Nothing rare is drawn twice in one pool.
- **Written by Claude** (Haiku, through L1): the biography, past memories, hook
  descriptions, voice and look, then a critic pass that rewrites what's generic.
- **Checked in code:** a local embedding model rejects a character too close to one
  already here, and traits are derived from values and temperament.
- `voice.needs_recording` is true when VoiceDesign can't do the accent, so the reference
  line has to be recorded and imported. `reference_clip` stays null until then.

## Spread

| Name structure | Characters |
|---|--:|
| given name and surname | 20 |

| Occupation category | Characters |
|---|--:|
| professionals | 3 |
| retired | 3 |
| service | 3 |
| student | 3 |
| clerical | 2 |
| operators | 2 |
| technicians | 2 |
| craft | 1 |
| not in work | 1 |

| Origin | Characters |
|---|--:|
| England | 4 |
| Italy | 2 |
| Poland | 2 |
| France | 1 |
| Germany | 1 |
| Iran | 1 |
| Ireland | 1 |
| New Zealand | 1 |
| Nigeria | 1 |
| Pakistan | 1 |
| Romania | 1 |
| Scotland | 1 |
| Turkey | 1 |
| United States | 1 |
| Wales | 1 |

| Age now | Characters |
|---|--:|
| 30s | 6 |
| 50s | 6 |
| 40s | 3 |
| under 20 | 2 |
| 20s | 1 |
| 60s | 1 |
| 70s | 1 |

| Gender | Characters |
|---|--:|
| man | 13 |
| woman | 7 |

| Arrival | Characters |
|---|--:|
| born here | 11 |
| for a fresh start after a break-up | 3 |
| with their family as a child | 2 |
| because the rent was cheap | 1 |
| for a job | 1 |
| to live with a partner | 1 |
| when they were offered social housing | 1 |

| Voice | Characters |
|---|--:|
| VoiceDesign | 13 |
| needs recording | 7 |

## Characters

| Character | Born | Origin | Occupation | Cares most about | Persona |
|---|--:|---|---|---|---|
| `andreas_schulz` Andreas Schulz | 1986 | Germany | Court clerk | obedience 0.86, discipline 0.83, pleasure 0.74 | He runs the filing side of the court and will not take a break until the last form on the tray is done, even when the break is well overdue. |
| `azadeh_rahimi` Azadeh Rahimi | 1973 | Iran | Florist | independence 0.89, adventure 0.89, freedom 0.87 | She runs the shop her way and ignores wholesale rules nobody has ever explained to her. |
| `berk_koc` Berk Koç | 1995 | Turkey | School secretary | pleasure 0.95, adventure 0.93, freedom 0.87 | Berk runs the front office as though he owns it, and will tell the head, the parents and the caretaker how things ought to go. |
| `brian_harris` Brian Harris | 1968 | United States | Retired call centre agent | tradition 0.91, optimism 0.89, connection 0.86 | He has the chairs out for quiz night a week early and knows whose bins go out on which day without being asked. |
| `chloe_edwards` Chloe Edwards | 2008 | England | Engineering student | adventure 0.98, optimism 0.97, creativity 0.96 | She arrives late with a rucksack of half-read books and a weekend plan that will have changed by Thursday. |
| `christine_turner` Christine Turner | 1955 | England | Retired toolmaker | compassion 0.81, creativity 0.80, equality 0.78 | She takes an apology at face value and has the kettle on before it's finished, and she'll have soup in a bowl for whoever's been ill before anyone asks. |
| `duncan_morrison` Duncan Morrison | 1973 | Scotland | Taxi driver | responsibility 0.98, honesty 0.94, loyalty 0.94 | He arrives early and checks the mileage twice, and he will hand back a fiver he was owed rather than let a fare feel short-changed. |
| `fergal_nolan` Fergal Nolan | 1987 | Ireland | School caretaker | security 0.87, obedience 0.73, pleasure 0.71 | He runs the school site the way he always has, and waves off any new ideas as fancy notions nobody asked for. |
| `funmilayo_oyelaran` Funmilayo Oyelaran | 1966 | Nigeria | Retired special needs teacher | security 0.79, loyalty 0.72, compassion 0.67 | She checks on the neighbours and will drop her own plans to sit with a worried child on the step, yet when anyone praises her she changes the subject. |
| `grzegorz_wozniak` Grzegorz Woźniak | 1989 | Poland | Payroll officer | optimism 0.97, success 0.96, obedience 0.89 | He learns the names of new starters before lunch and will chat to anyone at the bus stop as if they were already a friend. |
| `hamza_akhtar` Hamza Akhtar | 1994 | Pakistan | Journalist | equality 0.84, knowledge 0.75, self respect 0.69 | He spends weekends pulling council planning minutes and will correct a colleague's figure across the desk without softening it. |
| `ines_richard` Inès Richard | 1991 | France | Out of work | equality 0.98, connection 0.95, compassion 0.92 | She keeps her head down at the community hall and fetches the urn before anyone asks. |
| `iwan_pritchard` Iwan Pritchard | 1976 | Wales | Laundry machine operator | adventure 0.88, pleasure 0.70, independence 0.69 | He turns up late to everything, already talking about the next ride, and he waves off any plan that needs more than the minimum. |
| `james_wilson` James Wilson | 2006 | England | Trainee hairdresser | honesty 0.94, open mindedness 0.91, knowledge 0.86 | Careful, correct and a little rigid, he goes into every conversation already knowing what he thinks, and he says it straight, even when it costs him a friendship. |
| `marcin_pawlak` Marcin Pawlak | 1967 | Poland | Plasterer | tradition 0.94, obedience 0.93, security 0.91 | Each morning he sits on the same bench by the green until the first bus has gone past, and he doesn't move for anyone who asks him to. |
| `mariana_matei` Mariana Matei | 1969 | Romania | Nursery teacher | optimism 0.87, creativity 0.75, pleasure 0.71 | She greets every parent at the gate and tells them their child had a brilliant morning, then leaves the paperwork and the training courses to someone else. |
| `massimo_conti` Massimo Conti | 1979 | Italy | Sports massage therapist | success 0.90, self actualization 0.88, self respect 0.87 | He is already moving when the room wakes, with a new idea for the rota and a verdict on someone's posture before the kettle has boiled. |
| `neil_wright` Neil Wright | 1977 | England | HR adviser | obedience 0.97, security 0.96, success 0.96 | He keeps to the procedure and expects everyone else to. |
| `olivia_parata` Olivia Parata | 2008 | New Zealand | Trainee teacher | equality 0.97, connection 0.96, justice 0.95 | She speaks to the caretaker and the head teacher in one flat voice, and she'll correct a colleague's sum in front of the whole room. |
| `riccardo_greco` Riccardo Greco | 1995 | Italy | Hairdresser | success 0.93, tradition 0.90, security 0.87 | He runs the chair by the old rules and charges what the work is worth, not what the customer hopes to pay. |
