import type { PlayerStateMessage } from '../net';
import { hurts, type Hit, type Hurts } from './hurt';
import { percent } from './lamp-gauge';
import './health-gauge.css';

export const PULSE_SECONDS = 0.6;
const LEAST_PULSE = 0.5;

/** A hit's effect fading over its `seconds`, from its strength at first to nothing; overlapping ones keep the strongest. */
export class Fade {
  private strength = 0;
  private at = -Infinity;
  private seconds = 1;

  start(strength: number, now: number, seconds: number): void {
    if (this.left(now) > strength) return;
    this.strength = strength;
    this.at = now;
    this.seconds = seconds;
  }

  left(now: number): number {
    const t = (now - this.at) / this.seconds;
    return t >= 0 && t < 1 ? this.strength * (1 - t) : 0;
  }
}

export class HealthGauge {
  private readonly gauge: HTMLElement;
  private readonly fill: HTMLElement;
  private readonly lost: HTMLElement;
  private readonly pulsing = new Fade();
  private readonly stop: () => void;
  private readonly now: () => number;
  private drawnHealth = 1;
  private lostFrom = 1;

  constructor(corner: HTMLElement, source: Pick<Hurts, 'on'> = hurts, now = () => performance.now() / 1000) {
    this.now = now;
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
    this.lostFrom = this.drawnHealth;
    this.pulsing.start(Math.max(strength, LEAST_PULSE), now, PULSE_SECONDS);
  }

  update(state: PlayerStateMessage | undefined, now = this.now()): void {
    this.drawnHealth = state?.player.health ?? 1;
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
    this.gauge.remove();
  }
}
