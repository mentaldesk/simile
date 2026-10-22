import type { Buyer } from '../net';

/** Whether the buyer's keeper buys parts of the body or fits bionics, as the clinic's doctor does. */
export const isClinic = (buyer: Buyer): boolean =>
  Object.keys(buyer.parts ?? {}).length > 0 || (buyer.fittings ?? []).length > 0;
