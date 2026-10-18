# Character pool

Premade characters for the character library (#89). Each `<id>.json` is a `Character`,
generated from `server/` by

```bash
uv run simile characters generate --count 20 --seed 20
```

A rerun skips the characters already here, and the first characters of a seed's plan
are the same for any count, so a larger `--count` adds to the pool. Don't edit them by
hand: delete one and rerun to write it again, or rename one with
`uv run simile characters rename <id> "<new name>"`. `renames.json` records the
seed and slot of each renamed character, so a rerun doesn't write the name the plan
drew there again.

The pool has 20 characters, not the 30 #183 asks for: the user asked for
a small pool. A larger one waits for #89's question on pool size.

- **Jobs come first** (#235). The plan starts with two characters for each of the
  village's roles (`roles.toml`), whose jobs fit it. Of the rest, 7 in 10 have a job from
  `makers.toml`, people who make or think, and the others are over 60 with a trade from
  `occupations.toml`, working or retired.
- **Sampled in code** (`server/simile/characters/sheet.py`), from the tables in
  `content/characters/tables/`: the census skeleton, values spread across the pool,
  temperament, life events, a contradiction, wound, secret and want, mannerisms, the
  kinds of hook, and what one of their interests is about. Nothing rare is drawn twice in
  one pool, and job families and interests spread out.
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

| Fits the role | Characters |
|---|--:|
| none | 11 |
| maker_space_host | 3 |
| barista | 2 |
| cook | 2 |
| gallery_host | 2 |

| Job family | Characters |
|---|--:|
| personal_service | 3 |
| art | 2 |
| teaching_professionals | 2 |
| biology | 1 |
| bionics | 1 |
| building | 1 |
| earth | 1 |
| farmers | 1 |
| legal_social_associates | 1 |
| medicine | 1 |
| music | 1 |
| planning | 1 |
| plant_operators | 1 |
| robotics | 1 |
| science | 1 |
| writing | 1 |

| Origin | Characters |
|---|--:|
| England | 5 |
| Poland | 3 |
| Ireland | 2 |
| Bangladesh | 1 |
| Brazil | 1 |
| Ghana | 1 |
| Pakistan | 1 |
| Philippines | 1 |
| Portugal | 1 |
| Scotland | 1 |
| South Africa | 1 |
| Spain | 1 |
| Turkey | 1 |

| Age now | Characters |
|---|--:|
| 30s | 6 |
| 40s | 4 |
| 70s | 3 |
| 20s | 2 |
| 60s | 2 |
| under 20 | 2 |
| 50s | 1 |

| Gender | Characters |
|---|--:|
| man | 10 |
| woman | 10 |

| Arrival | Characters |
|---|--:|
| born here | 7 |
| to live with a partner | 3 |
| with their family as a child | 3 |
| for a job | 2 |
| to study and stayed | 2 |
| for a partner's job | 1 |
| for seasonal work and stayed | 1 |
| when they were offered social housing | 1 |

| Voice | Characters |
|---|--:|
| VoiceDesign | 10 |
| needs recording | 10 |

## Characters

| Character | Born | Origin | Occupation | Cares most about | Persona |
|---|--:|---|---|---|---|
| `abena_asamoah` Abena Asamoah | 1957 | Ghana | Retired factory machine operator | success 0.95, ambition 0.92, self respect 0.86 | She keeps a ledger for the vegetables she sells from her back gate and quotes the takings to the penny. |
| `alba_rodriguez` Alba Rodríguez | 1994 | Spain | Typeface designer | justice 0.95, compassion 0.91, freedom 0.90 | She arrives with a marked-up proof and the flaw in your plan already circled, and she credits whoever drew the first rough as readily as herself. |
| `brenda_haworth` Brenda Haworth | 1964 | England | Retired gardener | justice 0.92, compassion 0.86, connection 0.82 | She'll learn a stranger's name at the bus stop, then have their lift to hospital sorted before the bus comes. |
| `chloe_clarke` Chloe Clarke | 1994 | England | Quantum physicist building gravity sensors | adventure 0.80, tradition 0.79, self respect 0.78 | Chloe takes the fieldwork nobody else wants and talks to strangers on trains as though they owe her a straight answer. |
| `darragh_conroy` Darragh Conroy | 1987 | Ireland | Glaciologist reading ice cores | justice 0.89, compassion 0.87, peace of mind 0.86 | He stays late to recheck a junior's figures without being asked, and he takes the blame for a shared error before anyone else can point at it. |
| `donal_furlong` Donal Furlong | 1981 | Ireland | Soft-robotics researcher making grippers out of silicone | independence 0.94, freedom 0.93, open mindedness 0.92 | He arrives at meetings with a notebook of sketches and talks over whoever is presenting, certain his design is better. |
| `filip_sikora` Filip Sikora | 1993 | Poland | Transport planner mapping cycle networks | peace of mind 0.83, connection 0.79, security 0.77 | He answers messages within the hour and remembers which neighbour's child has the exam on Thursday. |
| `grzegorz_pietrzak` Grzegorz Pietrzak | 1975 | Poland | Stop-motion animator | obedience 0.80, discipline 0.78, optimism 0.77 | He is in the building before the call time, dressed for a room where nobody has invited him to sit down. |
| `joanna_gonzales` Joanna Gonzales | 2008 | Philippines | Barista | pleasure 0.97, adventure 0.93, independence 0.88 | She swaps shifts on a whim and books a Tuesday ferry to somewhere she's never been, then waves off any warning about her hours or her till. |
| `joaquim_sousa` Joaquim Sousa | 1955 | Portugal | Retired nursery teacher | ambition 0.85, success 0.84, peace of mind 0.69 | He is first to a handshake at any gathering and last out of a meeting that has gone his way. |
| `kamran_malik` Kamran Malik | 1986 | Pakistan | Cook | responsibility 0.98, compassion 0.96, obedience 0.95 | He runs the kitchen by checking every delivery against the sheet and telling any cook who skips a step exactly how it will go wrong, without raising his voice. |
| `kubra_kurt` Kübra Kurt | 2008 | Turkey | Chef | tradition 0.76, obedience 0.58, independence 0.56 | She runs her section by the book, but lets it slide when someone moves the prep order without asking, grumbling only under her breath. |
| `liam_ashworth` Liam Ashworth | 1998 | England | Barista | self respect 0.91, ambition 0.90, responsibility 0.89 | He works the morning queue and talks to whoever is nearest, and he knows how everyone takes their milk. |
| `luke_brindley` Luke Brindley | 1992 | England | Audiologist tuning cochlear implants over an app | freedom 0.93, adventure 0.93, optimism 0.90 | He strikes up conversation with whoever is standing near him in a queue and has their life story inside five minutes, then quietly fixes the fault before anyone else has noticed it. |
| `marcin_wozniak` Marcin Woźniak | 1985 | Poland | Structural engineer for earthquake-proof schools | ambition 0.97, success 0.93, self respect 0.87 | He is on site before the contractors and has the drawings marked up before anyone else has finished a coffee. |
| `marelize_steyn` Marelize Steyn | 1978 | South Africa | Folk fiddler who tours small halls | success 0.86, self actualization 0.83, discipline 0.69 | She reaches every hall early, squares the chairs, and moves the sound engineer's microphone before anyone can apologise, then plays the set without once looking up at the crowd. |
| `pauline_ormerod` Pauline Ormerod | 1953 | England | Retired primary school teacher | creativity 0.90, pleasure 0.88, equality 0.83 | She arrives at meetings with half a plan for the noticeboard and is gone before anyone reads the minutes. |
| `raimunda_pereira` Raimunda Pereira | 1951 | Brazil | Plant geneticist breeding drought-proof wheat | loyalty 0.92, discipline 0.88, honesty 0.86 | She is most at ease alone in the glasshouse and equally at ease close to her children, and does not feel she has to choose between them. |
| `ross_paterson` Ross Paterson | 1994 | Scotland | Ghostwriter of other people's memoirs | obedience 0.98, discipline 0.93, tradition 0.90 | He arrives ten minutes early with the chapter plan printed and the notes typed. |
| `sadia_majumder` Sadia Majumder | 2000 | Bangladesh | Epidemiologist tracking viruses through wastewater | knowledge 0.96, justice 0.95, honesty 0.90 | She is first into the lab and last to sign off a result, and she will correct a colleague's figure in front of the room without softening it. |
