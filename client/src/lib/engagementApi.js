/* Announcements, contact form, bookmarks. */
import { api } from "./api";

export const engagementApi = {
  announcements: () => api.get("/announcements/").then((r) => r.data),
  contact: (data) => api.post("/contact/", data).then((r) => r.data),
  bookmarks: () => api.get("/bookmarks/").then((r) => r.data),
  // `page` pins a bookmark to one page of a paginated product; omit it otherwise.
  toggleBookmark: (type, id, page) =>
    api.post("/bookmarks/toggle/", { type, id, page }).then((r) => r.data),
};
