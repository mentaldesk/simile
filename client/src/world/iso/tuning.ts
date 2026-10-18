/** A window much wider than this draws bigger pixels instead of more of the village. */
export const MAX_TILES_ACROSS = 20;

/** How long to wait for the sim time before drawing `DEFAULT_HOUR`. */
export const CLOCK_WAIT_MS = 1500;

/** A table and its chairs are one image, so a sitter sorts this many tiles nearer, in front of it. */
export const SITTING_NEARER = 0.5;

/** Real seconds and tiles for residents keeping still. */
export type IdleTuning = {
  /** How long between one weight shift and the next. */
  shiftEvery: readonly [number, number];
  shiftFor: number;
  /** How near someone must be to be turned to. */
  turnTiles: number;
  /** How long between glances at whoever is nearest, and how long each lasts. */
  glanceEvery: readonly [number, number];
  glanceFor: readonly [number, number];
};

export const IDLE: IdleTuning = {
  shiftEvery: [4, 11],
  shiftFor: 0.7,
  turnTiles: 3,
  glanceEvery: [6, 18],
  glanceFor: [2, 5],
};
