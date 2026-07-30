/*
 * Checkout confirmation modal: shown before Razorpay opens so the student can
 * review the line items, apply/remove a coupon, and see the original price,
 * discount and final payable amount — all priced by the backend (never the
 * client). Pressing Pay hands off to `startCheckout` (Razorpay, or a free-order
 * completion when a coupon zeroes the total).
 *
 * Open it by passing a non-empty `items` array (e.g. [{ type: "chapter", id }]);
 * pass `null` to keep it closed.
 */
import { useEffect, useState } from "react";
import { FiCheckCircle, FiCreditCard, FiTag } from "react-icons/fi";
import { Modal } from "./ui/Modal";
import { Button } from "./ui/Button";
import { Alert } from "./ui/Alert";
import { Input } from "./ui/Input";
import { Spinner } from "./ui/Spinner";
import { paymentApi } from "../lib/paymentApi";
import { startCheckout } from "../lib/checkout";
import { apiError } from "../lib/api";

// Whole rupees when exact; 2 decimals when a coupon leaves a fractional amount,
// so the displayed total/CTA always matches the paise actually charged.
const money = (v) => {
  const n = Number(v);
  return `₹${n.toFixed(Number.isInteger(n) ? 0 : 2)}`;
};

function TotalRow({ label, value, strong = false, tone = "text-ink" }) {
  return (
    <div className={`flex justify-between gap-3 ${strong ? "text-base font-bold text-ink" : "text-sm"}`}>
      <span className={strong ? "" : "text-ink-soft"}>{label}</span>
      <span className={strong ? "" : tone}>{value}</span>
    </div>
  );
}

export function CheckoutModal({ items, user, onClose, onSuccess, onUnconfigured }) {
  const open = Array.isArray(items) && items.length > 0;
  const itemsKey = open ? JSON.stringify(items) : null;

  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [code, setCode] = useState("");
  const [applied, setApplied] = useState(null); // { code, discount }
  const [couponError, setCouponError] = useState(null);
  const [applying, setApplying] = useState(false);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState(null);

  // (Re)load a fresh quote whenever the modal opens with a new item set.
  useEffect(() => {
    if (!open) return undefined;
    setQuote(null); setLoadError(null); setCode(""); setApplied(null);
    setCouponError(null); setPayError(null); setPaying(false);
    let alive = true;
    setLoading(true);
    paymentApi
      .quote(items)
      .then((q) => { if (alive) setQuote(q); })
      .catch((e) => { if (alive) setLoadError(apiError(e, "Could not load checkout. Please try again.")); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [itemsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyCoupon = async () => {
    const c = code.trim();
    if (!c || applying) return;
    setApplying(true); setCouponError(null);
    try {
      const q = await paymentApi.quote(items, c);
      setQuote(q);
      if (q.coupon?.applied) {
        setApplied({ code: q.coupon.code, discount: q.coupon.discount });
      } else {
        setApplied(null);
        setCouponError(q.coupon?.error || "That coupon can’t be applied.");
      }
    } catch (e) {
      setApplied(null);
      setCouponError(apiError(e, "Could not check that coupon."));
    } finally {
      setApplying(false);
    }
  };

  const removeCoupon = async () => {
    setApplied(null); setCode(""); setCouponError(null);
    setLoading(true);
    try {
      setQuote(await paymentApi.quote(items));
    } catch (e) {
      setLoadError(apiError(e, "Could not refresh checkout."));
    } finally {
      setLoading(false);
    }
  };

  const pay = () => {
    setPayError(null); setPaying(true);
    startCheckout({
      items,
      coupon: applied?.code || "",
      user,
      onSuccess: (res) => { setPaying(false); onClose?.(); onSuccess?.(res); },
      onUnconfigured: (order) => { setPaying(false); onClose?.(); onUnconfigured?.(order); },
      onError: (msg) => { setPaying(false); setPayError(msg); },
      onCancel: () => setPaying(false),
    });
  };

  // Exclude items already owned, and items covered by a higher-level bundle in the
  // same cart (the backend doesn't charge for those) so the list matches the total.
  const payable = (quote?.items || []).filter((i) => !i.owned && !i.covered);
  const subtotal = quote ? Number(quote.subtotal) : 0;
  const discount = quote ? Number(quote.discount) : 0;
  const total = quote ? Number(quote.total) : 0;
  const isFree = quote != null && total <= 0;

  // Don't let a click-outside/Esc close the modal mid-payment.
  const handleClose = paying ? () => {} : onClose;

  return (
    <Modal open={open} onClose={handleClose} title="Checkout">
      {loading && !quote ? (
        <div className="flex justify-center py-10 text-brand-600 dark:text-brand-300">
          <Spinner className="h-8 w-8" />
        </div>
      ) : loadError ? (
        <Alert tone="error">{loadError}</Alert>
      ) : quote ? (
        <div className="space-y-5">
          {/* Line items */}
          <ul className="space-y-2">
            {payable.map((it, i) => (
              <li key={i} className="flex justify-between gap-3 text-sm">
                <span className="min-w-0 truncate text-ink">{it.label}</span>
                <span className="shrink-0 font-semibold text-ink">{money(it.price)}</span>
              </li>
            ))}
          </ul>

          {/* Coupon */}
          {applied ? (
            <div className="flex items-center justify-between gap-3 rounded-2xl bg-teal-50 px-4 py-3 ring-1 ring-teal-100">
              <span className="flex min-w-0 items-center gap-2 text-sm font-semibold text-teal-700 dark:text-teal-300">
                <FiCheckCircle className="h-4 w-4 shrink-0" />
                <span className="truncate">Coupon {applied.code} applied</span>
              </span>
              <button
                type="button"
                onClick={removeCoupon}
                className="shrink-0 text-sm font-medium text-teal-700 hover:underline dark:text-teal-300"
              >
                Remove
              </button>
            </div>
          ) : (
            <div>
              <div className="flex items-start gap-2">
                <div className="flex-1">
                  <Input
                    type="text"
                    placeholder="Coupon code"
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase())}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); applyCoupon(); } }}
                    error={couponError}
                    aria-label="Coupon code"
                  />
                </div>
                <Button
                  variant="outline"
                  className="mt-0 shrink-0"
                  loading={applying}
                  disabled={!code.trim()}
                  icon={FiTag}
                  onClick={applyCoupon}
                >
                  Apply
                </Button>
              </div>
            </div>
          )}

          {/* Totals */}
          <div className="space-y-1.5 border-t border-line pt-4">
            <TotalRow label="Original price" value={money(subtotal)} />
            {discount > 0 && (
              <TotalRow label="Discount" value={`– ${money(discount)}`} tone="text-teal-700 dark:text-teal-300" />
            )}
            <div className="pt-1">
              <TotalRow label="Total payable" value={money(total)} strong />
            </div>
          </div>

          {payError && <Alert tone="error">{payError}</Alert>}

          <Button
            variant="premium"
            size="lg"
            icon={FiCreditCard}
            loading={paying}
            disabled={applying || loading || !quote}
            onClick={pay}
            className="w-full"
          >
            {isFree ? "Unlock for free" : `Pay ${money(total)}`}
          </Button>
          <p className="text-center text-xs text-ink-soft">
            Secure payment · amount verified on our server
          </p>
        </div>
      ) : null}
    </Modal>
  );
}
