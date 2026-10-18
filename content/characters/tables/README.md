# Character generation tables

The curated tables the character pool generator (P3, #183) samples from. Each file is TOML, loaded
and cross-checked by `simile.characters.tables.load_tables()`, which refuses to load a table that
refers to a field, value, score or id that doesn't exist.

## How a character is drawn

Each stage is conditioned on what's already decided, so the facts hang together, and each takes
what the player has fixed and samples only the rest:

1. **Census skeleton** (`sample_skeleton`): birth year, gender, origin, name, where they came from,
   class background, upbringing, the household they grew up in (one that fits the upbringing),
   siblings, education, partnership, children, health, work and occupation, in that order.
   `origins_for(country)` gives the origin ids for a locked country. Given `jobs`, as the pool's
   plan gives for a role or a maker, the job is drawn before education, so a job that needs a
   degree comes with one they've finished.
2. **Values**: `simile.npc.values`, unchanged.
3. **Temperament** (`sample_temperament`): HEXACO domains pulled by the values, facets around them.
4. **Life events** (`sample_events`): 2 to 6, conditioned on all of the above and on each other.
5. **Attachment** (`sample_attachment`): from temperament and childhood.
6. **Tension** (`sample_tension`): a contradiction, a wound, a secret and a want with its need.
7. **Mannerisms** (`sample_mannerisms`): from temperament.

A row's conditions:

| Key | Meaning |
|---|---|
| `when` | Census fields that must match: a list of values, `{ not = [...] }`, `{ min, max }` or `true`/`false` |
| `implied` | Census fields that make an event certain, like a divorce for the divorced |
| `after` | Earlier draws, one of which must have happened (for events, at a younger age) |
| `not_with` | Events it can't share a life with |
| `lean` | Core values and temperament scores, -3 to 3. A lean of 1 makes a score of 0.9 about five times as likely to draw as a score of 0.1 |
| `boost` | Multipliers for a `field=value` or an earlier draw's id |
| `years` | Calendar years an event can happen in (Covid, the 2008 crash) |
| `rare` | At most one resident per village |

Nothing may be conditioned on origin or gender, so no origin or gender is tied to a kind of job,
event or hardship. The loader enforces it.

A `Village` passed to the samplers records what one cast has drawn: no name part or job is used
twice, a rare event, secret or mannerism goes to one resident at most, and anything else gets less
likely each time a neighbour already has it, job families included. That is what stops three fraud
whistleblowers turning up in one village.

Outputs are plain dataclasses for P3 to map onto `Character`: a `Happening` has the age, the text
(which never states the age), an `impact` of 1 to 100 for a past memory's salience and a `valence`
of -1 to 1.

## Sources and licences

The repository has no licence file yet. "Written for this project" means the content was written
here and owes nothing to a third party.

| Table | Source | Licence |
|---|---|---|
| `names.toml` | Written for this project. See *Names* below. Origin weights are judgement, loosely following the largest countries of birth in England and Wales's 2021 Census ([ONS](https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/internationalmigration/bulletins/internationalmigrationenglandandwales/census2021)) plus the home nations | Names are facts; ONS figures under the Open Government Licence v3.0 |
| `census.toml` | Eurostat statistics for employment, education and health by age, the rest judgement. See *Census* below | Eurostat data: CC BY 4.0, reused with acknowledgement |
| `occupations.toml` | ISCO-08 groups (ILO) weighted by Eurostat's [lfsa_egai2d](https://ec.europa.eu/eurostat/databrowser/view/lfsa_egai2d/default/table) employment. See *Occupations* below | Eurostat data: CC BY 4.0; ISCO-08 codes and group names used as labels only |
| `makers.toml` | Written for this project. See *People who make or think* below | |
| `roles.toml` | Written for this project. See *The village's roles* below | |
| `events.toml` | Written for this project, with Holmes and Rahe (1967) as a starting point. See *Life events* below | A handful of published scores used as anchors, with citation |
| `tension.toml` | Written for this project | |
| `temperament.toml` | HEXACO domain and facet names (Lee and Ashton) and the four attachment styles (Bartholomew and Horowitz, 1991), with descriptions written for this project | Model names only; no inventory items are reproduced |
| `mannerisms.toml` | Generated once with Haiku through L1. See *Mannerisms* below | Generated for this project |

### Names

Given names for each origin, gender and birth era (born before 1965, 1965–1989, 1990 on), plus
surnames, written by hand from common names in each country and generation. No list was copied from
a dataset. To tighten the eras, check them against national statistics such as the ONS's baby names
for England and Wales, the US Social Security Administration's names by decade, Ireland's CSO,
Scotland's NRS, Spain's INE (most common names by decade of birth) and Brazil's IBGE *Nomes no
Brasil*.

- A country with very different naming communities is split, so a given name and a surname never
  come from different communities: India (Hindi, Gujarati, Malayali), Nigeria (Yoruba, Igbo) and
  South Africa (Afrikaans, isiZulu). Polish surnames are ones that don't change with gender.
- **Checked for slang and jokes**, for an English-speaking player especially, and left out:
  "Marites" (Filipino slang for a gossip), "Karen", "Kevin", "Kyle", "Chad", "Stacy", "Becky"
  (memes), "Butt", "Dong", "Fanny", "Randy", "Wood", Vietnamese "Phúc", "Dũng", "Hùng" and "Bích",
  Gujarati "Dave", "Harsh" and "Meet", Polish "Grażyna" and "Janusz" (memes in Poland), Australian
  "Bruce" and "Sheila", "Garfield", "Ariel", "Lucky", "Princess", "Purity", "Divan", "Lamia",
  "Can", and "Mario", "Luigi" and "Ferrari" together. `test_load.py` keeps them out. The most
  common names stay even when they look like an English word, such as Wang, Hồ, Đức and Hardik.
- **No real individuals.** Name lists hold no full names. Where a given name and a surname from the
  same origin would make a famous person, the full name is in that origin's `famous` list and the
  sampler never draws it (Hardik Pandya, Rohit Sharma, Thomas Müller, Paolo Rossi, Bruno
  Fernandes, Thiago Silva, Dylan Thomas, Noel Gallagher and others). A few given names were left
  out for the same reason (Imran, Efren, Romeo, Zain, Ji-eun, Chae-young, Mario, Larry, Luiz).

### Census

| Weight | Source |
|---|---|
| In work, by age | Eurostat [lfsa_ergan](https://ec.europa.eu/eurostat/databrowser/view/lfsa_ergan/default/table), EU-27, 2023, as published (85 and over set to 0) |
| Education, by age | Eurostat [edat_lfse_03](https://ec.europa.eu/eurostat/databrowser/view/edat_lfse_03/default/table), EU-27, 2023. ISCED 3–4 is split into general and vocational with the same table's ED34_44 and ED35_45. The 65–74 band is worked out from 55–64 and 55–74, taking the two halves of 55–74 as 53% and 47% of it. The 75+ band and the split of ISCED 5–8 into a degree (60%) and a postgraduate degree (40%) are judgement |
| Has a long-standing condition, by age | Eurostat [hlth_silc_05](https://ec.europa.eu/eurostat/databrowser/view/hlth_silc_05/default/table), EU-27, 2023. Which condition is judgement |
| Everything else | Judgement, aiming at the rough shape of European statistics: gender, born here, arrivals, class background and households, upbringing, siblings, partnership and children by age, the statuses of people not in work, and how background shifts education |

People still studying have the education level they're working towards, and are students. The
household someone grew up in comes from the kinds their upbringing allows: one naming both parents,
one parent raising them alone, or neither, so a two-parent upbringing never gets a mother raising
them alone.

### Occupations

Each ISCO-08 sub-major group's weight is its EU-27 employment in 2023, ages 15–64, in thousands,
from Eurostat's lfsa_egai2d. Its titles, written for this project, share that weight equally. ISCO-08
gives each group a skill level, and `[skill]` says how likely each education level is to hold a job
at each skill level, by judgement following ISCO-08's mapping of skill levels to ISCED. The age
limits on each job are judgement, so a 75-year-old can still keep a market stall but not drive a
train. Retired residents get a former job drawn as of age 55.

A group or a title marked `makes` is a job whose holder makes or studies something: science,
engineering and ICT professionals, the craft trades, and a few titles such as journalist and
musician. Casting's variety report (`simile cast-variety`) counts them with makers.toml's jobs and
students.

### People who make or think

`makers.toml` is the user's list of jobs for people who make or think (#235): researchers,
writers, artists, roboticists, builders, musicians, architects, planners, philosophers, founders
and game designers. Each job is one line, a title and its family, with `ages` and `degree` if they
differ from the family's. Titles are specific and a little near-future, like "prosthetics engineer
designing hands that can feel", and the loader refuses a line with an unknown family or key, or a
title that's already here or in `occupations.toml`. Each family's titles share a weight of 1, so
families are equally likely whatever their size.

A family's `major` is the ISCO-08 major group that `events.toml` conditions see, and `skill` its
ISCO-08 skill level. Jobs that wouldn't have existed a generation ago have upper age limits, so an
older maker gets a job that would have, like a philosopher or a choir director.

Adding or changing a line changes what the pool's plan draws, as any table does, so the pool test
(`test_rerunning_the_readme_command_would_write_nothing`) fails until the pool is regenerated.

### The village's roles

`roles.toml` names the people the village's interiors need: a barista for the Daily Grind, a cook
for Golden Bowl Noodles, and hosts for Spark Maker Space and the gallery. Each role lists the jobs
that fit it, as titles or makers.toml families, and the workplace, shifts and pay casting gives
whoever fills it. Casting fills the roles first, in this order, and the pool's plan starts with two
characters for each. The café's shift matches its opening hours in `simile.cafe`'s config. The
barista and the cook take their shop's takings. The hosts' pay is left for E3 (#243), which sets
what wages are worth.

### Life events

162 events, written for this project. Holmes and Rahe's Social Readjustment Rating Scale (*Journal
of Psychosomatic Research* 11, 1967) was the starting point for which kinds of event to include,
and anchors `impact` where an event maps onto one of its items: death of a spouse 100, divorce 73,
imprisonment 63, death of a close family member 63, personal injury or illness 53, marriage 50,
being fired 47. The wording is ours, not the scale's. Base weights, valence and conditions are
judgement. The events are plain and careful: no abuse, self-harm or graphic violence.

### Temperament and attachment

The six HEXACO domains and their 24 facets (Lee and Ashton, *Multivariate Behavioral Research* 39,
2004), with each end described in our own words. The HEXACO-PI-R's items are copyrighted and none
are used. How much each core value pulls a domain is judgement. The four attachment styles follow
Bartholomew and Horowitz (*Journal of Personality and Social Psychology* 61, 1991). Their base
weights (55% secure, 20% anxious, 15% dismissing, 10% fearful) are judgement anchored on Hazan and
Shaver's (1987) 56% secure, 25% avoidant and 19% anxious, with avoidant split between dismissing and
fearful.

### Mannerisms

Conversational habits only, each something a listener would notice from a resident's words alone:
verbal habits, the shape of how they talk, and humour and tone. Characters store one or two, and the
conversation prompts list them as verbal habits to use now and then.

Generated with Haiku through L1, on the local Claude Code login, by
`uv run python -m simile.characters.tables.generate_mannerisms`: 15 calls (16 with one retry), 18
mannerisms each, one for each end of the six HEXACO domains and three for anyone (verbal habits,
conversation shape, and humour and tone). Each group leans on its domain, so an outgoing resident
tends to get an outgoing mannerism. Deduplication kept 260 of 272, and curation by hand left 198: it
cut physical and written habits, good deeds, repeats across groups and English-village clichés, and
reworded a few.

Delete or reword freely, but keep the groups and keep every item audible in dialogue. Rerun
`--dedupe-only` afterwards to catch new repeats. The loader refuses an item over 120 characters, the
most a character can store.
