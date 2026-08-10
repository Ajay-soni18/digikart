/* Thin wrappers over the API client for the admin CRUD endpoints. */
import { api } from "../lib/api";

// Build a multipart body when a payload contains a File; otherwise send JSON.
function toFormData(payload) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(payload)) {
    if (v === null || v === undefined) continue;
    fd.append(k, v);
  }
  return fd;
}

function hasFile(payload) {
  return Object.values(payload).some((v) => v instanceof File);
}

export const adminApi = {
  overview: () => api.get("/admin/overview/").then((r) => r.data),
  catalogOverview: () => api.get("/admin/catalog-overview/").then((r) => r.data),
  users: (params) => api.get("/admin/users/", { params }).then((r) => r.data),
  revenue: (params) => api.get("/admin/revenue/", { params }).then((r) => r.data),
  transactions: (params) => api.get("/admin/transactions/", { params }).then((r) => r.data),

  // Generic resource CRUD. `resource` is e.g. "categories", "products", "bundles".
  list: (resource, params) =>
    api.get(`/admin/${resource}/`, { params }).then((r) => r.data),

  create: (resource, payload) => {
    if (hasFile(payload)) {
      // Pass Content-Type: undefined so the browser sets multipart/form-data
      // WITH the boundary (hardcoding the value omits the boundary and breaks it).
      // timeout: 0 disables the default request timeout — product files are large
      // and can take well over 30s to upload on a slow connection.
      return api
        .post(`/admin/${resource}/`, toFormData(payload), {
          headers: { "Content-Type": undefined },
          timeout: 0,
        })
        .then((r) => r.data);
    }
    return api.post(`/admin/${resource}/`, payload).then((r) => r.data);
  },

  update: (resource, id, payload) => {
    if (hasFile(payload)) {
      return api
        .patch(`/admin/${resource}/${id}/`, toFormData(payload), {
          headers: { "Content-Type": undefined },
          timeout: 0,
        })
        .then((r) => r.data);
    }
    return api.patch(`/admin/${resource}/${id}/`, payload).then((r) => r.data);
  },

  remove: (resource, id) => api.delete(`/admin/${resource}/${id}/`),

  // Create a product and, optionally, attach its first file in one action.
  //
  // Three calls are unavoidable: storage keys are `products/{id}/{version}/…`,
  // so the product must exist before its bytes can be stored. The admin sees one
  // button; this hides the sequence — but NOT the failure. If the product is
  // created and the upload then fails, we return the product along with the
  // error, because silently swallowing it is how you end up with a paid product
  // that has no file.
  createProductWithAttachment: async (payload) => {
    const { attachment, ...fields } = payload;
    const product = await adminApi.create("products", fields);
    if (!(attachment instanceof File)) return { product, uploadError: null };

    const isPdf = /\.pdf$/i.test(attachment.name);
    try {
      const row = await adminApi.create("product-files", {
        product: product.id,
        title: attachment.name,
        // Only a PDF can use the watermarked viewer. The upload endpoint
        // re-derives the real type from the bytes and downgrades anything else,
        // so this is a starting guess, not the final word.
        delivery: isPdf ? "protected" : "download",
        file_type: isPdf ? "pdf" : "other",
      });
      await adminApi.uploadFile(row.id, attachment);
      return { product, uploadError: null };
    } catch (e) {
      return { product, uploadError: e };
    }
  },

  // Replace a product file's bytes. Multipart, and untimed: these are large.
  uploadFile: (fileId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return api
      .post(`/admin/product-files/${fileId}/upload/`, fd, {
        headers: { "Content-Type": undefined },
        timeout: 0,
      })
      .then((r) => r.data);
  },

  // Site content (homepage/footer)
  getSiteContent: () => api.get("/site-content/").then((r) => r.data),
  saveSiteContent: (payload) =>
    api.patch("/site-content/", payload).then((r) => r.data),
};
