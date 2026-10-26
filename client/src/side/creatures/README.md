# Creatures

The tunnels' creatures (P10), from the server's `snapshot`, `creature_moved` and `creature_gone`
([`server/simile/creatures/`](../../../../server/simile/creatures/README.md)), drawn by `SideScene`
from their figures in [`content/creatures/`](../../../../content/creatures/README.md).

- `creatures.ts` keeps each one, tweening from where it's drawn to each new position over the time
  since the last, as the server sends one every 0.2 sim seconds while it moves. A move of more
  than 1.5 tiles, or onto another map, snaps. One that's gone keels over and fades for
  `DOWN_SECONDS` before it's dropped.
- `figures.ts` picks the pose by `docs/protocol.md`'s table and its frame: a walk or run cycle steps
  with the distance covered, anything else with time. Each frame is drawn with its anchor where the
  creature is, at the scene's scale (`PPM` over the figure's `ppm`), mirrored about the anchor to
  face west. Going down tips it on its back away from the way it faces, a bat dropping as it goes.
- `view.ts` draws the creatures on the street shown, just behind the residents, tinted with the
  light like them, and pink while `hurt`. The darkness covers them as it covers everything else.
