import type { Item, PlayerStateMessage } from '../net';
import { LAMP_KEY, lampHere, lampOf, LOW } from '../side/lamp';
import './lamp-gauge.css';

export type Where = { dark: boolean; plug: boolean };

export const percent = (charge: number): string => `${Math.round(charge * 100)}%`;

/** Green, then amber, then red as it runs down. */
export function level(charge: number): 'full' | 'half' | 'low' {
  if (charge > 0.5) return 'full';
  return charge > LOW ? 'half' : 'low';
}

export function lampHint(lamp: Item | undefined, { dark, plug }: Where): string | undefined {
  if (!lamp) return undefined;
  const charge = lamp.charge ?? 0;
  if (plug) return charge < 1 ? 'Charging your lamp.' : 'Your lamp is charged.';
  if (!charge) return dark ? "It's dark, and your lamp is flat. Charge it at a plug." : 'Your lamp is flat. Charge it at a plug.';
  if (dark && !lamp.on) return `It's dark. Press ${LAMP_KEY} for your lamp.`;
  if (lamp.on && charge <= LOW) return 'Your lamp is running low.';
  return undefined;
}

/** The lamp's battery in a corner, whether it's on or charging, and a hint when it matters. */
export class LampGauge {
  private readonly root: HTMLElement;
  private readonly fill: HTMLElement;
  private readonly state: HTMLElement;
  private readonly hint: HTMLElement;

  constructor(parent: HTMLElement) {
    this.root = parent.appendChild(document.createElement('div'));
    this.root.className = 'lamp-gauge';
    this.root.hidden = true;
    this.root.appendChild(document.createElement('kbd')).textContent = LAMP_KEY;
    const battery = this.root.appendChild(document.createElement('span'));
    battery.className = 'lamp-battery';
    this.fill = battery.appendChild(document.createElement('span'));
    this.state = this.root.appendChild(document.createElement('span'));
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'lamp-hint';
    this.hint.hidden = true;
  }

  update(message: PlayerStateMessage | undefined, where: Where = lampHere): void {
    const lamp = lampOf(message);
    this.root.hidden = !lamp;
    const hint = lampHint(lamp, where);
    this.hint.hidden = !hint;
    if (hint && this.hint.textContent !== hint) this.hint.textContent = hint;
    if (!lamp) return;
    const charge = lamp.charge ?? 0;
    this.fill.style.width = percent(charge);
    this.fill.className = `lamp-level-${level(charge)}`;
    const state = where.plug && charge < 1 ? '⚡' : lamp.on ? 'on' : 'off';
    if (this.state.textContent !== state) this.state.textContent = state;
    this.root.ariaLabel = `Lamp ${lamp.on ? 'on' : 'off'}, ${percent(charge)}`;
  }
}
