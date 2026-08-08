/*
 * Global cart bar: a fixed bottom bar shown on every page whenever the cart is
 * non-empty, so a buyer can keep adding items from anywhere in the catalog and
 * check them all out together from wherever they are.
 * Hidden when the cart is empty. Owns its own CheckoutModal; on success it
 * empties the cart and pings `notifyPurchase()` so the mounted page refreshes.
 */
import { useEffect, useRef, useState } from "react";
import { FiCheckCircle, FiCreditCard } from "react-icons/fi";
import { Button } from "./ui/Button";
import { CheckoutModal } from "./CheckoutModal";
import { useCart } from "../cart/CartContext";
import { useAuth } from "../auth/AuthContext";
import { paymentApi } from "../lib/paymentApi";
import { money } from "../lib/pricing";

export function CartBar() {
  const { items, count, clear, removeMany, purchaseVersion, notifyPurchase } = useCart();
  const { user, isAuthenticated } = useAuth();
  const [total, setTotal] = useState(null);
  const [checkoutItems, setCheckoutItems] = useState(null);
  const [flash, setFlash] = useState(null); // { msg, ok }
  const flashTimer = useRef(null);

  // Live (debounced) quote whenever the cart changes or a purchase lands. The
  // server is authoritative on price; we also drop any items it reports as
  // already owned (bought meanwhile via a bundle) so the cart can't dead-end at
  // a ₹0 "nothing to pay for" checkout.
  useEffect(() => {
    if (!count) {
      setTotal(null);
      return undefined;
    }
    setTotal(null);
    const t = setTimeout(() => {
      paymentApi
        .quote(items)
        .then((q) => {
          setTotal(Number(q.total));
          const owned = (q.items || []).filter((i) => i.owned);
          if (owned.length) removeMany(owned);
        })
        .catch(() => setTotal(null));
    }, 200);
    return () => clearTimeout(t);
  }, [items, count, purchaseVersion, removeMany]);

  useEffect(() => () => clearTimeout(flashTimer.current), []);

  const showFlash = (msg, ok = true) => {
    setFlash({ msg, ok });
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(null), 5000);
  };

  if (!isAuthenticated) return null;

  return (
    <>
      {flash && (
        <div className="fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-4">
          <div
            className={`flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold text-white shadow-lift ${
              flash.ok ? "bg-emerald-600" : "bg-navy-800"
            }`}
          >
            <FiCheckCircle className="h-4 w-4 shrink-0" />
            {flash.msg}
          </div>
        </div>
      )}

      {count > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line-strong bg-surface/95 px-4 py-3 shadow-lift backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
            <div className="text-sm">
              <span className="font-bold text-ink">
                {count} item{count > 1 ? "s" : ""} in cart
              </span>
              <span className="font-semibold text-gold-700 dark:text-gold-300">
                {" "}
                · {total == null ? "…" : money(total)}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={clear}>
                Clear
              </Button>
              <Button variant="premium" size="md" icon={FiCreditCard} onClick={() => setCheckoutItems(items)}>
                Checkout
              </Button>
            </div>
          </div>
        </div>
      )}

      <CheckoutModal
        items={checkoutItems}
        user={user}
        onClose={() => setCheckoutItems(null)}
        onSuccess={() => {
          clear();
          notifyPurchase();
          showFlash("Payment successful — your notes are unlocked! 🎉");
        }}
        onUnconfigured={() => showFlash("Payments aren’t enabled yet — please try again later.", false)}
      />
    </>
  );
}
