import type { Direction } from '../player';

/** Arrow keys move in screen directions: screen up is grid north-west, screen right north-east. */
export const gridDirection = ({ x, y }: Direction): Direction => ({ x: x + y, y: y - x });
