/*
 * General playlist page: lists every video of one general (dashboard) playlist,
 * stacked vertically — the same layout as a chapter's YouTube lectures, but with
 * a yellow (gold) accent to match the dashboard cards. Reached by clicking a
 * subheading card on the dashboard. Tapping a video plays it in the shared
 * nocookie YouTube modal.
 *
 * Data comes from the public general-videos endpoint (headings → playlists →
 * videos); we locate the playlist by its slug, mirroring how ChapterLectures
 * fetches a subject and picks the chapter out of it.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { YouTubeModal } from "../components/YouTubeModal";
import { Spinner } from "../components/ui/Spinner";
import { contentApi } from "../lib/contentApi";
import { FiPlay } from "react-icons/fi";

/* A single video row — thumbnail + details, gold-accented. */
function VideoRow({ video, onPlay }) {
  return (
    <div className="group relative flex flex-col overflow-hidden rounded-2xl bg-surface shadow-card ring-1 ring-gold-200/70 transition hover:shadow-lift sm:flex-row">
      <button
        onClick={() => onPlay(video)}
        aria-label={`Play ${video.title}`}
        className="relative block w-full shrink-0 sm:w-64 md:w-72"
      >
        <div className="relative aspect-video bg-navy-100">
          {video.thumbnail_url && (
            <img src={video.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" />
          )}
          <span className="absolute inset-0 grid place-items-center">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-surface/95 text-gold-600 dark:text-gold-300 shadow-lift transition group-hover:scale-110">
              <FiPlay className="h-5 w-5 translate-x-[1px]" />
            </span>
          </span>
          {video.duration && (
            <span className="absolute bottom-2 right-2 rounded bg-navy-900/85 px-1.5 py-0.5 text-xs font-medium text-white">{video.duration}</span>
          )}
        </div>
      </button>

      <div className="flex flex-1 items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <button onClick={() => onPlay(video)} className="block text-left">
            <p className="font-semibold text-ink">{video.title}</p>
          </button>
          {video.description && (
            <p className="mt-1 line-clamp-2 text-sm text-ink-soft">{video.description}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function GeneralPlaylistPage() {
  const { slug } = useParams();
  const [headings, setHeadings] = useState(null);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(null);

  useEffect(() => {
    setHeadings(null);
    setError(null);
    contentApi.generalVideos().then(setHeadings).catch(() => setError("Could not load this playlist."));
  }, [slug]);

  // Locate the playlist (and its parent heading) by slug.
  const found = useMemo(() => {
    if (!headings) return null;
    for (const heading of headings) {
      const playlist = heading.playlists.find((p) => p.slug === slug);
      if (playlist) return { heading, playlist };
    }
    return null;
  }, [headings, slug]);

  useEffect(() => {
    if (found) document.title = `${found.playlist.title} · Digikart`;
  }, [found]);

  if (error) return <Shell><div className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:text-red-300">{error}</div></Shell>;
  if (!headings) return <Shell><div className="flex justify-center py-20 text-gold-600 dark:text-gold-300"><Spinner className="h-9 w-9" /></div></Shell>;
  if (!found) return <Shell><div className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:text-red-300">Playlist not found.</div></Shell>;

  const { heading, playlist } = found;
  const videos = playlist.videos || [];

  return (
    <Shell>
      <nav className="mb-3 flex flex-wrap items-center gap-1 text-sm text-ink-soft">
        <Link to="/dashboard" className="font-medium text-gold-700 dark:text-gold-300 hover:underline">Dashboard</Link>
        <span className="text-gold-400">/</span>
        <span>{heading.title}</span>
        <span className="text-gold-400">/</span>
        <span className="font-medium text-ink">{playlist.title}</span>
      </nav>

      <h1 className="text-3xl font-extrabold tracking-tight text-ink">{playlist.title}</h1>
      {playlist.description && <p className="mt-1 text-ink-soft">{playlist.description}</p>}

      <div className="mt-6 space-y-4">
        {videos.length === 0 ? (
          <div className="rounded-card border border-dashed border-gold-200 bg-surface/60 p-10 text-center text-ink-soft">
            No videos in this playlist yet.
          </div>
        ) : (
          videos.map((v) => <VideoRow key={v.id} video={v} onPlay={setPlaying} />)
        )}
      </div>

      <YouTubeModal lecture={playing} onClose={() => setPlaying(null)} />
    </Shell>
  );
}

function Shell({ children }) {
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-8">{children}</main>
      <Footer />
    </div>
  );
}
