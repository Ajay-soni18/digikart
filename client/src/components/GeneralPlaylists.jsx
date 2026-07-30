/*
 * Dashboard-only general videos — admin-created headings (e.g. "The Academic
 * Edge"), each rendered like an MBBS year: the heading title followed by a grid
 * of subheading (playlist) cards. The cards match the subject-card dimensions
 * but use a yellow (gold) accent and a film icon, to read as distinct from the
 * blue subject cards. Clicking a card opens that playlist's videos on its own
 * page. These sections render ABOVE the MBBS years.
 *
 * Headings/playlists with no published videos are skipped, so nothing blank
 * ever shows.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { FiFilm, FiArrowRight } from "react-icons/fi";
import { Spinner } from "./ui/Spinner";
import { contentApi } from "../lib/contentApi";

/* One playlist (subheading) card — mirrors SubjectCard's layout/size, gold-tinted. */
function PlaylistCard({ playlist, onOpen }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(playlist)}
      className="group flex items-center justify-between gap-3 rounded-card border border-gold-200/70 bg-gradient-to-br from-gold-50 to-surface p-5 text-left shadow-card transition hover:-translate-y-0.5 hover:shadow-lift dark:from-gold-500/10 dark:to-surface"
    >
      <div>
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-ink">{playlist.title}</span>
        </div>
        <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-gold-700 dark:text-gold-300 group-hover:gap-1.5">
          Watch playlist <FiArrowRight className="h-3.5 w-3.5 transition-all" />
        </span>
      </div>
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-gold-100 text-gold-600 dark:text-gold-300">
        <FiFilm className="h-5 w-5" />
      </span>
    </button>
  );
}

export function GeneralPlaylists() {
  const navigate = useNavigate();
  const [headings, setHeadings] = useState(null);

  useEffect(() => {
    contentApi
      .generalVideos()
      .then((data) =>
        // Keep only playlists that have videos, then only headings that still
        // have at least one such playlist.
        setHeadings(
          (data || [])
            .map((h) => ({ ...h, playlists: h.playlists.filter((p) => p.videos.length > 0) }))
            .filter((h) => h.playlists.length > 0),
        ),
      )
      .catch(() => setHeadings([])); // a fetch failure simply hides the row
  }, []);

  const openPlaylist = (p) => navigate(`/playlists/${p.slug}`);

  // Loading: a small inline spinner so the dashboard doesn't jump.
  if (headings === null) {
    return (
      <div className="mt-8 flex justify-center py-6 text-brand-600 dark:text-brand-300">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (headings.length === 0) return null; // nothing to show — render nothing

  return (
    <div className="mt-8 space-y-10">
      {headings.map((heading) => (
        <section key={heading.id}>
          <div className="mb-4 flex items-center gap-2">
            <h2 className="text-xl font-bold text-ink">{heading.title}</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {heading.playlists.map((p) => (
              <PlaylistCard key={p.id} playlist={p} onOpen={openPlaylist} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
