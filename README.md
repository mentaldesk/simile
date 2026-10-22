# #357's previews: the player, visibly bionic

- `real-client.jpg`, and each shot in `real-client/`: the real client's side view (`?harness=side`, on
  the High Street at 2× device pixels), with a `player_state` dispatched for each combination of bionics,
  standing, walking, jumping and facing west. The eye is fitted in the right socket.
- `sheets/all.jpg`: every frame of every combination, as shipped (overlays), from the atlases.
- `sheets/<combination>.jpg`: that combination three ways: overlays (shipped), full edits' first pass,
  and full edits' second pass with the eye and the kept datajack asked for again.
- `scripts/`: how these were made. `full-edits/` is the full-edit pipeline (`server/simile/dolls/`'s
  `bionics.py` and `build.py` as they were for the comparison), `shots.ts` takes the screenshots
  (`node shots.ts <client dir> <out dir> [map] [x]`, from a folder with the client's `node_modules`),
  `grid.py` and `sheet.py` draw the grid and the sheets.
