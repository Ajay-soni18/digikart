/*
 * Razorpay checkout orchestration, shared by the subject cart and the locked
 * notes viewer.
 *
 *   createOrder (backend, server-priced)
 *     → open Razorpay widget (checkout.js, loaded in index.html)
 *     → on success, backend VERIFIES the signature and grants entitlements
 *
 * If live keys aren't configured yet, the backend returns keys_configured=false
 * and we surface a friendly notice instead of opening a broken widget.
 */
import { apiError } from "./api";
import { paymentApi } from "./paymentApi";

export async function startCheckout({ items, coupon, user, onSuccess, onError, onUnconfigured, onCancel }) {
  let order;
  try {
    order = await paymentApi.createOrder(items, coupon);
  } catch (e) {
    onError?.(apiError(e, "Could not start checkout."));
    return;
  }

  // Coupon brought the total to ₹0 → the backend already completed a free order
  // and granted access. No Razorpay widget needed.
  if (order.free_order) {
    onSuccess?.(order);
    return;
  }

  if (!order.keys_configured) {
    onUnconfigured?.(order);
    return;
  }
  if (!window.Razorpay) {
    onError?.("Payment library failed to load. Please refresh and try again.");
    return;
  }

  const rzp = new window.Razorpay({
    key: order.key_id,
    amount: order.amount,
    currency: order.currency,
    name: "Digikart",
    description: "Notes purchase",
    order_id: order.razorpay_order_id,
    prefill: { name: user?.full_name, email: user?.email },
    theme: { color: "#a229c3" },
    // User closed/cancelled the widget without paying → release the coupon slot
    // the order was holding, then let the caller reset its loading state so the
    // checkout button is re-enabled (no refresh needed).
    modal: {
      ondismiss: () => {
        paymentApi.cancelOrder(order.order_db_id).catch(() => {});
        onCancel?.();
      },
    },
    handler: async (resp) => {
      try {
        const res = await paymentApi.verify({
          razorpay_order_id: resp.razorpay_order_id,
          razorpay_payment_id: resp.razorpay_payment_id,
          razorpay_signature: resp.razorpay_signature,
        });
        if (res.status === "success") onSuccess?.(res);
        else onError?.("Payment could not be verified.");
      } catch (e) {
        onError?.(apiError(e, "Payment verification failed."));
      }
    },
  });
  rzp.on("payment.failed", () => onError?.("Payment failed or was cancelled."));
  rzp.open();
}
