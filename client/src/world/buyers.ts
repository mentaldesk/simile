import type { Buyer } from '../net';

/** Whether the buyer's keeper buys parts of the body or fits bionics, as the clinic's doctor does. */
export const fits = (buyer: Buyer): boolean => Object.keys(buyer.parts ?? {}).length > 0 || (buyer.fittings ?? []).length > 0;

/** Whether E opens the buyer's panel rather than selling at once: it fits, or sells something back. */
export const isClinic = (buyer: Buyer): boolean => fits(buyer) || (buyer.stock ?? []).length > 0;
