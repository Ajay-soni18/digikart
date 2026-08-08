/* Public catalog reads. The api client attaches the user's token when present,
   so `unlocked` flags always reflect who is asking. */
import { api } from "./api";

export const catalogApi = {
  // The whole published navigation tree in one call — it's small, and every
  // page's navigation needs it.
  tree: () => api.get("/categories/").then((r) => r.data),
  category: (slug) => api.get(`/categories/${slug}/`).then((r) => r.data),
  product: (slug) => api.get(`/products/${slug}/`).then((r) => r.data),
  search: (q) => api.get("/search/", { params: { q } }).then((r) => r.data),
};
