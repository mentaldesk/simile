import { PPM } from './layout';
import type { LayerName } from './scenery';

/** How much of the street the view shows, top to bottom, unless the window is too narrow. */
export const VIEW_HEIGHT_M = 19;
export const MIN_VIEW_WIDTH_M = 16;
/** How far down the view the street's feet line sits, and the highest and lowest the player's
 * feet go, as on a dollhouse's top floor or down by the river. */
export const FEET_AT = 0.82;
export const HEADROOM = 0.3;
export const FOOTROOM = 0.84;
/** How quickly the camera catches up, a share of the gap a second. */
export const FOLLOW_RATE = 6;

export type Size = { width: number; height: number };
export type Point = { x: number; y: number };

/** Canvas px per world px: the street `VIEW_HEIGHT_M` tall, or `MIN_VIEW_WIDTH_M` wide. */
export function sideZoom(canvas: Size): number {
  return Math.min(canvas.height / (VIEW_HEIGHT_M * PPM), canvas.width / (MIN_VIEW_WIDTH_M * PPM));
}

/** Where the view's middle goes: on the player along the street, kept on the street where it's
 * wider than the view, and at street level unless the player climbs high or goes down below it. */
export function viewCentre(player: Point, streetFeet: number, streetWidth: number, view: Size, out: Point): Point {
  const half = view.width / 2;
  out.x = streetWidth <= view.width ? streetWidth / 2 : Math.min(Math.max(player.x, half), streetWidth - half);
  const top = Math.min(streetFeet - FEET_AT * view.height, player.y - HEADROOM * view.height);
  out.y = Math.max(top, player.y - FOOTROOM * view.height) + view.height / 2;
  return out;
}

/** The view's middle at street level, the reference the layers' heights are given at. */
export const streetCentreY = (streetFeet: number, view: Size): number =>
  streetFeet - FEET_AT * view.height + view.height / 2;

/** Eases the camera towards its target, framerate-independent. */
export function follow(current: Point, target: Point, dt: number, out: Point): Point {
  const t = 1 - Math.exp(-FOLLOW_RATE * dt);
  out.x = current.x + (target.x - current.x) * t;
  out.y = current.y + (target.y - current.y) * t;
  return out;
}

/** Each street layer's height and where its bottom sits, in metres below the feet line (up is
 * negative): #309's previews' composition. The sky fills the view and the ground is the map's. */
export const LAYER_PLACES: Record<Exclude<LayerName, 'sky' | 'ground'>, { bottom: number; height?: number }> = {
  far: { bottom: -7.5, height: 5.75 },
  mid: { bottom: -2.75, height: 6.25 },
  near: { bottom: 0.1 },
  foreground: { bottom: 4.3, height: 2.8 },
};

/** Where a layer is drawn for a camera: copies `width` apart from `first`, `count` of them, moved
 * `parallax` as far as the camera along x, and up and down. */
export type Copies = { first: number; count: number; y: number };

export function layerCopies(
  parallax: number,
  width: number,
  view: { left: number; width: number; centre: Point },
  baseY: number,
  streetY: number,
  out: Copies,
): Copies {
  const shift = view.centre.x * (1 - parallax);
  const k = Math.floor((view.left - shift) / width);
  out.first = k * width + shift;
  out.count = Math.ceil((view.left + view.width - out.first) / width) + 1;
  out.y = baseY + (view.centre.y - streetY) * (1 - Math.min(parallax, 1));
  return out;
}
