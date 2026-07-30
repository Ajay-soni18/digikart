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
  users: (params) => api.get("/admin/users/", { params }).then((r) => r.data),
  revenue: (params) => api.get("/admin/revenue/", { params }).then((r) => r.data),
  transactions: (params) => api.get("/admin/transactions/", { params }).then((r) => r.data),

  // Generic resource CRUD. `resource` is e.g. "years", "subjects", "notes".
  list: (resource, params) =>
    api.get(`/admin/${resource}/`, { params }).then((r) => r.data),

  create: (resource, payload) => {
    if (hasFile(payload)) {
      // Pass Content-Type: undefined so the browser sets multipart/form-data
      // WITH the boundary (hardcoding the value omits the boundary and breaks it).
      // timeout: 0 disables the default request timeout — note PDFs are large and
      // can take well over 30s to upload on a slow connection.
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

  // Bulk operations for the admin content tree's multi-select.
  // `fields` is a map of boolean flags, e.g. { is_published: true }.
  bulkUpdate: (resource, ids, fields) =>
    api.post(`/admin/${resource}/bulk-update/`, { ids, fields }).then((r) => r.data),
  bulkRemove: (resource, ids) =>
    api.post(`/admin/${resource}/bulk-delete/`, { ids }).then((r) => r.data),

  // Bulk-import a YouTube playlist's videos into a chapter as Lecture rows.
  // timeout: 0 — large playlists make several paginated YouTube calls server-side.
  importPlaylist: (chapter, playlistUrl) =>
    api
      .post(
        "/admin/lectures/import-playlist/",
        { chapter, playlist_url: playlistUrl },
        { timeout: 0 },
      )
      .then((r) => r.data),

  // Bulk-import a YouTube playlist into a general (dashboard) video section.
  // timeout: 0 — large playlists make several paginated YouTube calls server-side.
  importGeneralPlaylist: (section, playlistUrl) =>
    api
      .post(
        "/admin/general-videos/import-playlist/",
        { section, playlist_url: playlistUrl },
        { timeout: 0 },
      )
      .then((r) => r.data),

  // Site content (homepage/footer)
  getSiteContent: () => api.get("/site-content/").then((r) => r.data),
  saveSiteContent: (payload) =>
    api.patch("/site-content/", payload).then((r) => r.data),
};
