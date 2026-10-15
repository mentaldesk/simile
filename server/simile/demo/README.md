# simile.demo

A dev mode that walks the fixture NPCs around the village, so the client has something moving
before the NPCs' real behaviour (B1) exists. It's off unless you ask for it:

```bash
SIMILE_DEMO=1 make dev                            # sim server and client
cd server && SIMILE_DEMO=1 uv run simile serve    # server only
```

Each NPC starts on its doorstep, a few seconds after the one before, and walks two errands (the
coffee shop, the square, the park or a terminal) and home again, resting at each stop, over and
over. It drives W2's movement (`simile.world`), so the `entity_moved` messages are exactly what
the real behaviour will send, and the snapshot puts everyone where movement has them.

It never runs under `simile headless`. Don't combine it with W2's `SIMILE_DEMO_WALK`, which walks
Mei too.
