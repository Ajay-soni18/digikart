/* Public content reads (years grid + subject tree). The api client attaches the
   user's token when present, so `unlocked` flags reflect who's asking. */
import { api } from "./api";

export const contentApi = {
  years: () => api.get("/years/").then((r) => r.data),
  subject: (slug) => api.get(`/subjects/${slug}/`).then((r) => r.data),
  generalVideos: () => api.get("/general-videos/").then((r) => r.data),
  search: (q) => api.get("/search/", { params: { q } }).then((r) => r.data),
};
