/*
 * Cart line-item helpers shared across the buy surfaces.
 *
 * Items are `{ type: "product" | "bundle", id }` and are keyed by (type, id) —
 * a product id and a bundle id can collide, so the type is always part of the
 * key. The coverage helpers mirror the backend's `resolve_cart` rule so that
 * adding a bundle can supersede (remove) its members from the cart, and a
 * bundle and its own contents never sit in the cart together.
 *
 * This is a display convenience only. The backend re-checks coverage on every
 * quote and order, so a client that ignores all of this still cannot be charged
 * twice for the same thing.
 */
export const cartKey = (type, id) => `${type}:${id}`;

export const productPairs = (products) =>
  (products || []).map((p) => ({ type: "product", id: p.id }));

// Everything a bundle covers: its member products, and any nested bundles the
// server told us about.
export const bundleDescendantPairs = (bundle) => [
  ...productPairs(bundle?.products),
  ...(bundle?.bundles || []).map((b) => ({ type: "bundle", id: b.id })),
];

// A product the buyer can add to the cart on its own: locked, priced, not free.
export const isProductSellable = (product) =>
  !product.unlocked && !product.is_free && Number(product.price) > 0;

export const sellableProducts = (products) => (products || []).filter(isProductSellable);

// How a product row should render on a category page:
//   "coming_soon" — placeholder, not clickable
//   "owned"       — already unlocked; link to open it, no buy control
//   "covered"     — a bundle containing it is already in the cart
//   "buyable"     — sellable on its own → Add-to-cart
//   "free"        — no payment needed; plain link
export function productRowState(product, { coveringBundleInCart = false } = {}) {
  if (product.is_coming_soon) return "coming_soon";
  if (product.unlocked) return "owned";
  if (coveringBundleInCart) return "covered";
  if (product.is_free) return "free";
  return isProductSellable(product) ? "buyable" : "free";
}
