/** The renders are made to be drawn 1:1: a 96 × 48 px diamond has the area of today's 48 px tile. */
export const ISO_ZOOM = 1;

/** Today's 16 × 24 px atlases stand in for A2b's sprites, at the size they're drawn top-down. */
export const PLACEHOLDER_SCALE = 3;
export const FIGURE_HEIGHT = 24 * PLACEHOLDER_SCALE;

/** How long to wait for the sim time before drawing the default lighting set. */
export const CLOCK_WAIT_MS = 1500;
