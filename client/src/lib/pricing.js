/*
 * Client-side price helpers — DISPLAY ONLY. The backend re-prices every cart
 * authoritatively at checkout (see apps/payments/pricing.py); these just render
 * estimates and format amounts. A chapter exposes its computed whole-chapter
 * price as `bundle_price` (null when it isn't sold as a bundle); otherwise its
 * roll-up value is the sum of its (non-free) note prices, and units/subjects roll
 * up their children the same way.
 */

// Whole rupees with the ₹ symbol.
export const money = (v) => `₹${Number(v).toFixed(0)}`;

export const chapterCost = (c) => {
  if (c.is_free) return 0;
  if (c.bundle_price != null) return Number(c.bundle_price);
  return (c.notes || []).reduce((s, n) => s + (n.is_free ? 0 : Number(n.price)), 0);
};

export const unitPrice = (u) =>
  u.bundle_price != null
    ? Number(u.bundle_price)
    : (u.chapters || []).reduce((s, c) => s + chapterCost(c), 0);

export const subjectPrice = (s) =>
  s.bundle_price != null
    ? Number(s.bundle_price)
    : (s.units || []).reduce((t, u) => t + unitPrice(u), 0);
