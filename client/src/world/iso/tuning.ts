/** A window much wider than this draws bigger pixels instead of more of the village. */
export const MAX_TILES_ACROSS = 20;

/** The cell of every character sheet, with the feet at `anchor`: `characters.json`. */
export const FRAME = { width: 72, height: 129, anchor: { x: 36, y: 110 } } as const;

/** From the feet to the top of the head. */
export const FIGURE_HEIGHT = 96;

/** How long to wait for the sim time before drawing `DEFAULT_HOUR`. */
export const CLOCK_WAIT_MS = 1500;
