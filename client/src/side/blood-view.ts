import Phaser from 'phaser';
import type { Hit } from '../ui/hurt';
import { attackerOf } from './attacker';
import { Blood, alphaOf } from './blood';
import { DEPTH } from './depths';
import { feetOf, xOf } from './layout';
import type { Village } from './maps';
import type { SidePlayer } from './player';

const RED = 0x9c0c0c;

const multiply = (a: number, b: number) =>
  [16, 8, 0].reduce<number>((colour, shift) => colour | (Math.round((((a >> shift) & 0xff) * ((b >> shift) & 0xff)) / 255) << shift), 0);

export class BloodView {
  private readonly blood = new Blood();
  private readonly graphics: Phaser.GameObjects.Graphics;
  private inside = false;

  constructor(scene: Phaser.Scene) {
    this.graphics = scene.add.graphics();
  }

  hit({ strength }: Hit, player: SidePlayer, village: Village): void {
    this.inside = village.map(player.drawnMap)?.kind === 'floor';
    const attacker = attackerOf(player.mapPosition);
    const away = attacker ? Math.sign(player.mapPosition.x - attacker.at.x) : 0;
    this.blood.burst(strength, { x: xOf(player.at.x), y: feetOf(player.at.y) }, feetOf(player.ground), away);
    this.graphics.setDepth((this.inside ? DEPTH.insideDoll : DEPTH.doll) + 0.5);
  }

  clear(): void {
    this.blood.clear();
  }

  update(dt: number, light: { inside: number; ground: number }): void {
    this.blood.update(dt);
    const { graphics } = this;
    graphics.clear();
    const colour = multiply(RED, light[this.inside ? 'inside' : 'ground']);
    for (const drop of this.blood.drops) {
      graphics.fillStyle(colour, alphaOf(drop));
      if (drop.landed) {
        graphics.fillEllipse(drop.x, drop.y, drop.radius * 3, drop.radius);
        continue;
      }
      graphics.fillCircle(drop.x, drop.y, drop.radius);
      const speed = Math.hypot(drop.vx, drop.vy) || 1;
      const tail = drop.radius * 1.4;
      graphics.fillCircle(drop.x - (drop.vx / speed) * tail, drop.y - (drop.vy / speed) * tail, drop.radius * 0.55);
    }
  }

  destroy(): void {
    this.graphics.destroy();
  }
}
