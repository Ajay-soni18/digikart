/*
 * Client-side price helpers — DISPLAY ONLY. The backend re-prices every cart
 * authoritatively at checkout (see apps/catalog/pricing.py); these only format
 * amounts and add up what's on screen.
 *
 * The flat catalog needs far less arithmetic here than the old hierarchy did:
 * products and bundles both arrive with a server-computed `price`, so there is
 * nothing to roll up client-side.
 */

// Whole rupees with the ₹ symbol.
export const money = (v) => `₹${Number(v || 0).toFixed(0)}`;

// What a product costs on its own (0 when it's free).
export const productCost = (p) => (p?.is_free ? 0 : Number(p?.price || 0));

// A cart line's price, whichever kind it is.
export const lineCost = (item) => Number(item?.price || 0);

// Sum of the lines the buyer will actually be charged for. Lines already owned,
// or covered by a bundle in the same cart, cost nothing.
export const payableTotal = (lines = []) =>
  lines.reduce((total, line) => (line.owned || line.covered ? total : total + lineCost(line)), 0);
