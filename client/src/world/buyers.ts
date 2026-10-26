import type { Buyer } from '../net';

/** Whether the buyer's keeper buys parts of the body, fits bionics or treats, as the clinic's doctor does. */
export const fits = (buyer: Buyer): boolean =>
  Object.keys(buyer.parts ?? {}).length > 0 || (buyer.fittings ?? []).length > 0 || (buyer.treatments ?? []).length > 0;

export const trades = (buyer: Buyer): boolean => fits(buyer) || (buyer.stock ?? []).length > 0;
