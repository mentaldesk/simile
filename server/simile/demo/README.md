# simile.demo

A dev mode that walks the fixture NPCs around the village, so the client has something moving
before the NPCs' real behaviour (B1) exists. It's off unless you ask for it:

```bash
SIMILE_DEMO=1 make dev                            # sim server and client
cd server && SIMILE_DEMO=1 uv run simile serve    # server only
```

Each NPC leaves its doorstep on two errands (the coffee shop, the square, the park or a terminal),
pausing at each, then goes home and starts again. They walk at `WALKING_SPEED` along the shortest
route over walkable tiles of the village map, diagonals included, and publish `EntityMoved` each
time they reach a tile, as W2's movement does. The snapshot puts them on the last tile they reached.

It never runs under `simile headless`, and tests don't turn it on.
