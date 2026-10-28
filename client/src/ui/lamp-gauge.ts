import type { Item, PlayerStateMessage } from '../net';
import { LAMP_KEY, lampHere, lampOf, LOW } from '../side/lamp';
import { onCell } from './hunger';
import './lamp-gauge.css';

export type Where = { dark: boolean; plug: boolean };

export const percent = (charge: number): string => `${Math.round(charge * 100)}%`;

/** Charge from which the gauge warns to charge, as power's does, and from which it warns the light's about to go. */
export const LOW_LAMP = 0.3;
export const NEARLY_FLAT = 0.1;

/** Green, then amber, then red as it runs down. */
export function level(charge: number): 'full' | 'half' | 'low' {
  if (charge > 0.5) return 'full';
  return charge > LOW ? 'half' : 'low';
}

/** `power` is the cell's charge, once one is in. */
export function lampHint(lamp: Item | undefined, { dark, plug }: Where, power?: number): string | undefined {
  if (plug && power !== undefined && power < 1) {
    return lamp && (lamp.charge ?? 0) < 1 ? 'Charging your lamp and your cell.' : 'Charging your cell.';
  }
  if (!lamp) return undefined;
  const charge = lamp.charge ?? 0;
  if (plug) return charge < 1 ? 'Charging your lamp.' : 'Your lamp is charged.';
  if (!charge) return dark ? "It's dark, and your lamp is flat. Charge it at a plug." : 'Your lamp is flat. Charge it at a plug.';
  if (dark && !lamp.on) return `It's dark. Press ${LAMP_KEY} for your lamp.`;
  if (charge <= NEARLY_FLAT) return "Your lamp is nearly flat. Charge it at a plug, or you'll be in the dark.";
  if (charge <= LOW_LAMP) return 'Your lamp is low. Charge it at a plug.';
  return undefined;
}

/** Whether the gauge flashes: low, and not at a plug. */
export const warning = (charge: number, { plug }: Where): boolean => charge > 0 && charge <= LOW_LAMP && !plug;

function battery(row: HTMLElement): HTMLElement {
  const outline = row.appendChild(document.createElement('span'));
  outline.className = 'lamp-battery';
  return outline.appendChild(document.createElement('span'));
}

/** The lamp's battery in a corner, whether it's on or charging, the power cell's below it once one is in, and a hint when it matters. */
export class LampGauge {
  private readonly root: HTMLElement;
  private readonly fill: HTMLElement;
  private readonly state: HTMLElement;
  private readonly power: HTMLElement;
  private readonly powerFill: HTMLElement;
  private readonly powerState: HTMLElement;
  private readonly hint: HTMLElement;

  constructor(parent: HTMLElement) {
    this.root = parent.appendChild(document.createElement('div'));
    this.root.className = 'lamp-gauge';
    this.root.hidden = true;
    this.root.appendChild(document.createElement('kbd')).textContent = LAMP_KEY;
    this.fill = battery(this.root);
    this.state = this.root.appendChild(document.createElement('span'));
    this.power = parent.appendChild(document.createElement('div'));
    this.power.className = 'power-gauge';
    this.power.hidden = true;
    this.power.appendChild(document.createElement('span')).textContent = 'Power';
    this.powerFill = battery(this.power);
    this.powerState = this.power.appendChild(document.createElement('span'));
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'lamp-hint';
    this.hint.hidden = true;
  }

  update(message: PlayerStateMessage | undefined, where: Where = lampHere): void {
    const lamp = lampOf(message);
    const power = message && onCell(message.player) ? (message.player.power ?? 1) : undefined;
    this.root.hidden = !lamp;
    this.showPower(power, where);
    const hint = lampHint(lamp, where, power);
    this.hint.hidden = !hint;
    if (hint && this.hint.textContent !== hint) this.hint.textContent = hint;
    if (!lamp) return;
    const charge = lamp.charge ?? 0;
    this.fill.style.width = percent(charge);
    this.fill.className = `lamp-level-${level(charge)}`;
    this.root.classList.toggle('lamp-gauge-warning', warning(charge, where));
    const state = where.plug && charge < 1 ? '⚡' : lamp.on ? 'on' : 'off';
    if (this.state.textContent !== state) this.state.textContent = state;
    this.root.ariaLabel = `Lamp ${lamp.on ? 'on' : 'off'}, ${percent(charge)}`;
  }

  private showPower(power: number | undefined, where: Where): void {
    this.power.hidden = power === undefined;
    if (power === undefined) return;
    this.powerFill.style.width = percent(power);
    this.powerFill.className = `lamp-level-${level(power)}`;
    const state = where.plug && power < 1 ? '⚡' : '';
    if (this.powerState.textContent !== state) this.powerState.textContent = state;
    this.power.ariaLabel = `Power ${percent(power)}`;
  }
}
