/* Announcements, contact form, bookmarks, progress. */
import { api } from "./api";

export const engagementApi = {
  announcements: () => api.get("/announcements/").then((r) => r.data),
  contact: (data) => api.post("/contact/", data).then((r) => r.data),
  bookmarks: () => api.get("/bookmarks/").then((r) => r.data),
  // `page` is used for per-page note bookmarks; omit it for whole-object kinds (lectures).
  toggleBookmark: (type, id, page) =>
    api.post("/bookmarks/toggle/", { type, id, page }).then((r) => r.data),
  progress: () => api.get("/progress/").then((r) => r.data),
  markLecture: (id, completed) =>
    api.post(`/progress/lecture/${id}/`, { completed }).then((r) => r.data),
};
