import type { PlayerStateMessage } from '../net';
import { hurts, type Hit, type Hurts } from './hurt';
import { percent } from './lamp-gauge';
import './hurt-view.css';

export const FLASH_SECONDS = { least: 0.3, most: 0.65 };
export const PULSE_SECONDS = 0.6;
/** Px the red reaches in from the overlay's edges, 640 × 360 at least. */
const FLASH_PX = { least: 40, most: 80 };
export const FLASH_OPACITY = { least: 0.65, most: 1 };

const lerp = (range: { least: number; most: number }, t: number) => range.least + (range.most - range.least) * t;

/** A hit's effect fading over its `seconds`, from its strength at first to nothing; overlapping ones keep the strongest. */
export class Fade {
  private strength = 0;
  private at = -Infinity;
  private seconds = 1;

  /** False, leaving it be, while what's left of the last is stronger. */
  start(strength: number, now: number, seconds: number): boolean {
    if (this.left(now) > strength) return false;
    this.strength = strength;
    this.at = now;
    this.seconds = seconds;
    return true;
  }

  /** How much is left: `strength` when it starts, falling to 0. */
  left(now: number): number {
    const t = (now - this.at) / this.seconds;
    return t >= 0 && t < 1 ? this.strength * (1 - t) : 0;
  }
}

/** Getting hurt, for the player to see: the screen's edges flash red, and the health gauge in the hunger corner pulses. */
export class HurtView {
  private readonly flash: HTMLElement;
  private readonly gauge: HTMLElement;
  private readonly fill: HTMLElement;
  private readonly lost: HTMLElement;
  private readonly flashing = new Fade();
  private readonly pulsing = new Fade();
  private readonly stop: () => void;
  private readonly now: () => number;
  private drawnHealth = 1;
  private lostFrom = 1;

  constructor(parent: HTMLElement, corner: HTMLElement, source: Pick<Hurts, 'on'> = hurts, now = () => performance.now() / 1000) {
    this.now = now;
    this.flash = parent.insertBefore(document.createElement('div'), parent.firstChild);
    this.flash.className = 'hurt-flash';
    this.flash.hidden = true;
    this.gauge = corner.insertBefore(document.createElement('div'), corner.firstChild);
    this.gauge.className = 'health-gauge';
    this.gauge.hidden = true;
    this.gauge.appendChild(document.createElement('span')).textContent = 'Health';
    const bar = this.gauge.appendChild(document.createElement('span'));
    bar.className = 'health-bar';
    this.lost = bar.appendChild(document.createElement('span'));
    this.lost.className = 'health-lost';
    this.fill = bar.appendChild(document.createElement('span'));
    this.fill.className = 'health-fill';
    this.stop = source.on((hit) => this.hit(hit));
  }

  hit({ strength }: Hit, now = this.now()): void {
    if (this.flashing.start(lerp(FLASH_OPACITY, strength), now, lerp(FLASH_SECONDS, strength))) {
      const px = lerp(FLASH_PX, strength);
      this.flash.style.boxShadow = `inset 0 0 ${px}px ${px / 3}px #c81010`;
    }
    this.lostFrom = this.drawnHealth;
    this.pulsing.start(Math.max(strength, 0.5), now, PULSE_SECONDS);
  }

  update(state: PlayerStateMessage | undefined, now = this.now()): void {
    this.drawnHealth = state?.player.health ?? 1;
    const flash = this.flashing.left(now);
    this.flash.hidden = flash === 0;
    this.flash.style.opacity = flash.toFixed(3);
    const pulse = this.pulsing.left(now);
    this.gauge.hidden = !state || (this.drawnHealth >= 1 && pulse === 0);
    this.gauge.classList.toggle('health-gauge-pulsing', pulse > 0);
    this.gauge.style.setProperty('--pulse', pulse.toFixed(3));
    this.fill.style.width = percent(this.drawnHealth);
    this.lost.style.width = percent(pulse > 0 ? Math.max(this.lostFrom, this.drawnHealth) : this.drawnHealth);
    this.gauge.ariaLabel = `Health ${percent(this.drawnHealth)}`;
  }

  destroy(): void {
    this.stop();
    this.flash.remove();
    this.gauge.remove();
  }
}
