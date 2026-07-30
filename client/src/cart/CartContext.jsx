/*
 * Global cart.
 *
 * Students add items — individual notes, a whole chapter, a whole unit, or a
 * whole subject — and check them out together (possibly spanning different
 * chapters, subjects or years). The cart lives ABOVE the router so it survives
 * navigating between pages, and is mirrored to localStorage so it survives a full
 * reload. Line items are `{ type: "note" | "chapter" | "unit" | "subject", id }`;
 * the backend prices and authorises everything at checkout, and never charges for
 * an item already covered by a higher-level item in the same cart.
 *
 * Items are keyed by (type, id): a note id and a chapter id can collide, so every
 * helper takes the type too.
 *
 * `purchaseVersion` is bumped after any successful purchase so the page that is
 * currently mounted can refresh its `unlocked` flags, without each checkout site
 * needing to know how that page loads its data.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";

const CartContext = createContext(null);
const STORAGE_KEY = "digikart_cart";
const VALID_TYPES = ["note", "chapter", "unit", "subject"];
const keyOf = (type, id) => `${type}:${id}`;

// Read the persisted cart: the owner's user id plus well-formed line items.
function loadInitial() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    const rawItems = Array.isArray(parsed.items) ? parsed.items : [];
    const seen = new Set();
    const items = [];
    for (const i of rawItems) {
      if (!i || !VALID_TYPES.includes(i.type) || !Number.isFinite(Number(i.id))) continue;
      const k = keyOf(i.type, Number(i.id));
      if (seen.has(k)) continue;
      seen.add(k);
      items.push({ type: i.type, id: Number(i.id) });
    }
    return { ownerId: parsed.ownerId ?? null, items };
  } catch {
    return { ownerId: null, items: [] };
  }
}

export function CartProvider({ children }) {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id ?? null;

  const [boot] = useState(loadInitial); // read localStorage once
  const [items, setItems] = useState(boot.items);
  const [ownerId, setOwnerId] = useState(boot.ownerId);
  const [purchaseVersion, setPurchaseVersion] = useState(0);

  // Mirror to localStorage (with its owner) so the cart survives a full reload.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ ownerId, items }));
    } catch {
      /* storage full / unavailable — the in-memory cart still works */
    }
  }, [ownerId, items]);

  // Bind the cart to the logged-in user. If the active account changes (a
  // different person signs in on this device, even after the previous token
  // silently expired), reset the cart so one student never inherits another's.
  useEffect(() => {
    if (userId == null) return; // logged out is handled below
    if (ownerId == null) {
      setOwnerId(userId); // first known user adopts the restored cart
    } else if (ownerId !== userId) {
      setItems([]); // different account → start clean
      setOwnerId(userId);
    }
  }, [userId, ownerId]);

  // Drop the cart on logout (or session expiry) so a different account on this
  // device starts clean. Only fires on the authenticated→unauthenticated edge,
  // never on the initial bootstrap, so a reload by the same user keeps the cart.
  const wasAuth = useRef(isAuthenticated);
  useEffect(() => {
    if (wasAuth.current && !isAuthenticated) {
      setItems([]);
      setOwnerId(null);
    }
    wasAuth.current = isAuthenticated;
  }, [isAuthenticated]);

  const has = useCallback(
    (type, id) => items.some((i) => i.type === type && i.id === id),
    [items]
  );
  const add = useCallback(
    (type, id) =>
      setItems((c) => (c.some((i) => i.type === type && i.id === id) ? c : [...c, { type, id }])),
    []
  );
  const remove = useCallback(
    (type, id) => setItems((c) => c.filter((i) => !(i.type === type && i.id === id))),
    []
  );
  const toggle = useCallback(
    (type, id) =>
      setItems((c) =>
        c.some((i) => i.type === type && i.id === id)
          ? c.filter((i) => !(i.type === type && i.id === id))
          : [...c, { type, id }]
      ),
    []
  );
  // Remove a batch of items, each given as { type, id } (used to strip owned
  // items after a purchase, and to supersede children when a parent is added).
  const removeMany = useCallback((pairs) => {
    const drop = new Set((pairs || []).map((p) => keyOf(p.type, p.id)));
    if (!drop.size) return;
    setItems((c) =>
      c.some((i) => drop.has(keyOf(i.type, i.id))) ? c.filter((i) => !drop.has(keyOf(i.type, i.id))) : c
    );
  }, []);
  const clear = useCallback(() => setItems([]), []);
  const notifyPurchase = useCallback(() => setPurchaseVersion((v) => v + 1), []);

  const value = useMemo(
    () => ({ items, count: items.length, has, add, remove, toggle, removeMany, clear, purchaseVersion, notifyPurchase }),
    [items, has, add, remove, toggle, removeMany, clear, purchaseVersion, notifyPurchase]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside <CartProvider>");
  return ctx;
}
