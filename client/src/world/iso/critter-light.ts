import type { Point } from '../view';
import type { LightMap, LitLayer } from './lighting';

/** Tints from each light map at the tiles' middles, blended in between, read once so nothing is allocated. */
export class CritterLight {
  private readonly width: number;
  private readonly height: number;
  private readonly tints = new WeakMap<LightMap, Float64Array>();
  private readonly here = new Float64Array(3);
  private readonly sum = new Float64Array(3);

  constructor(width: number, height: number) {
    this.width = width;
    this.height = height;
  }

  colourAt(lit: readonly LitLayer[], at: Point): number {
    const { width, height, here, sum } = this;
    const fromLeft = at.x - 0.5;
    const fromTop = at.y - 0.5;
    let column = (fromLeft | 0) > fromLeft ? (fromLeft | 0) - 1 : fromLeft | 0;
    let row = (fromTop | 0) > fromTop ? (fromTop | 0) - 1 : fromTop | 0;
    let across = fromLeft - column;
    let down = fromTop - row;
    if (column < 0) {
      column = 0;
      across = 0;
    }
    if (row < 0) {
      row = 0;
      down = 0;
    }
    if (column > width - 1) column = width - 1;
    if (row > height - 1) row = height - 1;
    const right = column < width - 1 ? 3 : 0;
    const below = row < height - 1 ? width * 3 : 0;
    const corner = (row * width + column) * 3;
    sum.fill(0);
    for (let i = 0; i < lit.length; i++) {
      const { weight, light, lightMap } = lit[i];
      const tints = this.tintsOf(lightMap);
      for (let k = 0; k < 3; k++) {
        const top = tints[corner + k] * (1 - across) + tints[corner + right + k] * across;
        const bottom = tints[corner + below + k] * (1 - across) + tints[corner + below + right + k] * across;
        here[k] = light.tint[k] * (top * (1 - down) + bottom * down);
      }
      let over = here[0] > 1 ? here[0] : 1;
      if (here[1] > over) over = here[1];
      if (here[2] > over) over = here[2];
      for (let k = 0; k < 3; k++) sum[k] += (weight * here[k]) / over;
    }
    let colour = 0;
    for (let k = 0; k < 3; k++) {
      const channel = sum[k] < 0 ? 0 : sum[k] > 1 ? 1 : sum[k];
      colour = (colour << 8) | ((channel * 255 + 0.5) | 0);
    }
    return colour;
  }

  private tintsOf(lightMap: LightMap): Float64Array {
    let tints = this.tints.get(lightMap);
    if (tints) return tints;
    tints = new Float64Array(this.width * this.height * 3);
    for (let row = 0; row < this.height; row++) {
      for (let column = 0; column < this.width; column++) {
        tints.set(lightMap.tintAt({ x: column + 0.5, y: row + 0.5 }), (row * this.width + column) * 3);
      }
    }
    this.tints.set(lightMap, tints);
    return tints;
  }
}
