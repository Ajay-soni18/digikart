/* Payment endpoints. Prices are computed server-side; the client only sends
   which items are in the cart. */
import { api } from "./api";

export const paymentApi = {
  quote: (items, coupon) => api.post("/payments/quote/", { items, coupon }).then((r) => r.data),
  createOrder: (items, coupon) =>
    api.post("/payments/create-order/", { items, coupon }).then((r) => r.data),
  verify: (payload) => api.post("/payments/verify/", payload).then((r) => r.data),
  // Best-effort release of a coupon slot when the buyer abandons checkout.
  cancelOrder: (orderDbId) =>
    api.post("/payments/cancel-order/", { order_db_id: orderDbId }).then((r) => r.data),
};
