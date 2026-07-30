/*
 * Cart line-item helpers shared across the buy surfaces.
 *
 * Items are `{ type: "note" | "chapter" | "unit" | "subject", id }` and are keyed
 * by (type, id) — a note id and a chapter id can collide, so the type is always
 * part of the key. The descendant-pair helpers list everything a higher-level
 * item covers, so that adding a parent can supersede (remove) its children from
 * the cart — mirroring the backend's `resolve_cart` coverage rule and keeping a
 * bundle and its own contents from ever sitting in the cart together.
 */
export const cartKey = (type, id) => `${type}:${id}`;

export const notePairs = (notes) => (notes || []).map((n) => ({ type: "note", id: n.id }));

export const chapterNotePairs = (chapter) => notePairs(chapter?.notes);

export const unitDescendantPairs = (unit) =>
  (unit.chapters || []).flatMap((c) => [{ type: "chapter", id: c.id }, ...chapterNotePairs(c)]);

export const subjectDescendantPairs = (subject) =>
  (subject.units || []).flatMap((u) => [{ type: "unit", id: u.id }, ...unitDescendantPairs(u)]);

// A note the student can add to the cart on its own: locked, priced, not free.
export const isNoteSellable = (note) =>
  !note.unlocked && !note.is_free && Number(note.price) > 0;

export const sellableNotes = (notes) => (notes || []).filter(isNoteSellable);

// How a chapter row should render in the subject Notes tab:
//   "coming_soon" — placeholder, not clickable
//   "owned"       — already unlocked; link to read, no buy control
//   "covered"     — a parent unit/subject bundle is already in the cart
//   "buyable"     — has a purchasable bundle and/or sellable notes → Add-to-cart
//   "plain"       — nothing to buy (e.g. only free notes); plain link
export function chapterRowState(chapter, { unitInCart = false, subjectInCart = false } = {}) {
  if (chapter.is_coming_soon) return "coming_soon";
  if (chapter.unlocked) return "owned";
  if (unitInCart || subjectInCart) return "covered";
  const buyable = chapter.bundle_purchasable || sellableNotes(chapter.notes).length > 0;
  return buyable ? "buyable" : "plain";
}
