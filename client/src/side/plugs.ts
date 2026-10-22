import type Phaser from 'phaser';
import { DEPTH } from './depths';
import { feetOf, PPM, xOf } from './layout';
import type { Placed, SideMap, Village } from './maps';

const PLATE_M = { width: 0.3, height: 0.42, up: 0.6 };

const overlaps = (a: Placed, b: Placed) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** The plugs on a street and its floors that no piece of furniture draws, in street cells. */
export function bareSockets(village: Village, street: SideMap): { x: number; y: number; inside: boolean }[] {
  const maps = [street, ...street.buildings.flatMap(({ name }) => village.floors(name))];
  return maps.flatMap((map) =>
    map.interactables
      .filter((plug) => plug.type === 'plug' && !map.furniture.some((piece) => overlaps(piece, plug)))
      .map((plug) => ({ x: map.offset.x + plug.x, y: map.offset.y + plug.y + plug.h - 1, inside: map.kind === 'floor' })),
  );
}

/** A wall socket drawn in code at each bare plug, behind its building's front. */
export function drawSockets(scene: Phaser.Scene, village: Village, street: SideMap): Phaser.GameObjects.Graphics[] {
  const [w, h] = [PLATE_M.width * PPM, PLATE_M.height * PPM];
  return bareSockets(village, street).map(({ x, y, inside }) => {
    const plate = scene.add.graphics({ x: xOf(x), y: feetOf(y) - PLATE_M.up * PPM });
    plate.fillStyle(0x3d4a52).fillRoundedRect(-w / 2, -h / 2, w, h, 6);
    plate.lineStyle(3, 0x1d2b26).strokeRoundedRect(-w / 2, -h / 2, w, h, 6);
    const bolt = [
      [0.12, -0.38],
      [-0.2, 0.04],
      [0.0, 0.04],
      [-0.1, 0.38],
      [0.22, -0.06],
      [0.02, -0.06],
    ].map(([px, py]) => ({ x: px * w, y: py * h }));
    plate.fillStyle(0xf2c94c).fillPoints(bolt, true);
    plate.fillStyle(0x7fd06a).fillCircle(w * 0.3, -h * 0.36, 3.5);
    return plate.setDepth(inside ? DEPTH.frame : DEPTH.streetFurniture);
  });
}
