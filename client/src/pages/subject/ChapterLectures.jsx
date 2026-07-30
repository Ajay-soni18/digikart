/*
 * Chapter videos page: lists every YouTube lecture of a single chapter,
 * stacked vertically (one below another). Reached from the subject page's
 * Lectures tab. Data comes from the existing subject tree (no extra API) —
 * we fetch the subject and pick the chapter out of it.
 *
 * Bookmarks + "mark complete" behave exactly as they did on the subject page;
 * tapping a video plays it in the same nocookie YouTube modal.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { AppHeader } from "../../components/AppHeader";
import { Footer } from "../../components/Footer";
import { ComingSoon, ComingSoonBadge } from "../../components/ComingSoon";
import { YouTubeModal } from "../../components/YouTubeModal";
import { Spinner } from "../../components/ui/Spinner";
import { contentApi } from "../../lib/contentApi";
import { engagementApi } from "../../lib/engagementApi";
import { FiPlay, FiStar, FiCheck } from "react-icons/fi";

/* A single video, laid out horizontally (thumbnail + details) so the list
   reads as a clean vertical stack. Same surface/brand styling as before. */
function LectureRow({ lecture, onPlay, saved, done, onToggleSave, onToggleDone }) {
  return (
    <div className="group relative flex flex-col overflow-hidden rounded-2xl bg-surface shadow-card ring-1 ring-brand-100/70 transition hover:shadow-lift sm:flex-row">
      <button
        onClick={() => onPlay(lecture)}
        aria-label={`Play ${lecture.title}`}
        className="relative block w-full shrink-0 sm:w-64 md:w-72"
      >
        <div className="relative aspect-video bg-navy-100">
          {lecture.thumbnail_url && (
            <img src={lecture.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" />
          )}
          <span className="absolute inset-0 grid place-items-center">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-surface/95 text-brand-600 dark:text-brand-300 shadow-lift transition group-hover:scale-110">
              <FiPlay className="h-5 w-5 translate-x-[1px]" />
            </span>
          </span>
          {lecture.duration && (
            <span className="absolute bottom-2 right-2 rounded bg-navy-900/85 px-1.5 py-0.5 text-xs font-medium text-white">{lecture.duration}</span>
          )}
        </div>
      </button>

      <div className="flex flex-1 items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <button onClick={() => onPlay(lecture)} className="block text-left">
            <p className="font-semibold text-ink">{lecture.title}</p>
          </button>
          {lecture.description && (
            <p className="mt-1 line-clamp-2 text-sm text-ink-soft">{lecture.description}</p>
          )}
          <button
            onClick={() => onToggleDone(lecture.id)}
            className={`mt-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition ${
              done ? "bg-teal-100 text-teal-700 dark:text-teal-300" : "bg-navy-100 text-navy-600 hover:bg-navy-200"
            }`}
          >
            {done && <FiCheck className="h-3.5 w-3.5" />}
            {done ? "Completed" : "Mark complete"}
          </button>
        </div>

        <button
          onClick={() => onToggleSave(lecture.id)}
          aria-label={saved ? "Remove bookmark" : "Save lecture"}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-canvas shadow-card transition hover:scale-105"
        >
          <FiStar className={`h-4 w-4 ${saved ? "fill-gold-400 text-gold-500" : "text-ink-soft"}`} />
        </button>
      </div>
    </div>
  );
}

export default function ChapterLectures() {
  const { slug, chapterId } = useParams();

  const [subject, setSubject] = useState(null);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(null);

  const [savedSet, setSavedSet] = useState(() => new Set());
  const [doneSet, setDoneSet] = useState(() => new Set());
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);

  const load = useCallback(() => {
    return contentApi.subject(slug).then(setSubject);
  }, [slug]);

  useEffect(() => {
    setSubject(null);
    setError(null);
    load().catch(() => setError("Could not load this chapter."));
  }, [load]);

  useEffect(() => {
    engagementApi.progress()
      .then((p) => setDoneSet(new Set(p.completed_lecture_ids)))
      .catch(() => {});
    engagementApi.bookmarks()
      .then((bms) => setSavedSet(new Set(bms.filter((b) => b.kind === "lecture").map((b) => b.object_id))))
      .catch(() => {});
  }, []);

  // Locate the chapter (and its parent unit) within the subject tree.
  const found = useMemo(() => {
    if (!subject) return null;
    for (const unit of subject.units) {
      const chapter = unit.chapters.find((c) => String(c.id) === String(chapterId));
      if (chapter) return { unit, chapter };
    }
    return null;
  }, [subject, chapterId]);

  useEffect(() => {
    if (found) document.title = `${found.chapter.name} · ${subject.name} · Digikart`;
  }, [found, subject]);

  const toggleSave = (lectureId) => {
    setSavedSet((s) => {
      const next = new Set(s);
      next.has(lectureId) ? next.delete(lectureId) : next.add(lectureId);
      return next;
    });
    engagementApi.toggleBookmark("lecture", lectureId).catch(() => {});
  };

  const toggleDone = (lectureId) => {
    const willComplete = !doneSet.has(lectureId);
    setDoneSet((s) => {
      const next = new Set(s);
      willComplete ? next.add(lectureId) : next.delete(lectureId);
      return next;
    });
    engagementApi.markLecture(lectureId, willComplete).catch(() => {});
  };

  if (error) return <Shell><div className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:text-red-300">{error}</div></Shell>;
  if (!subject) return <Shell><div className="flex justify-center py-20 text-brand-600 dark:text-brand-300"><Spinner className="h-9 w-9" /></div></Shell>;
  if (!found) return <Shell><div className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:text-red-300">Chapter not found.</div></Shell>;

  const { unit, chapter } = found;
  const lectures = chapter.lectures || [];
  const visibleLectures = bookmarkedOnly ? lectures.filter((l) => savedSet.has(l.id)) : lectures;

  return (
    <Shell>
      <nav className="mb-3 flex flex-wrap items-center gap-1 text-sm text-ink-soft">
        <Link to="/dashboard" className="font-medium text-brand-700 dark:text-brand-300 hover:underline">Dashboard</Link>
        <span className="text-brand-300">/</span>
        <Link to={`/subjects/${slug}`} className="font-medium text-brand-700 dark:text-brand-300 hover:underline">{subject.name}</Link>
        <span className="text-brand-300">/</span>
        <span>{unit.name}</span>
        <span className="text-brand-300">/</span>
        <span className="font-medium text-ink">{chapter.name}</span>
      </nav>

      <div className="flex items-center gap-3">
        <h1 className="text-3xl font-extrabold tracking-tight text-ink">{chapter.name}</h1>
        {chapter.is_coming_soon && <ComingSoonBadge />}
      </div>
      <p className="mt-1 text-ink-soft">{unit.name}</p>

      {lectures.length > 0 && (
        <div className="mt-6 flex justify-end">
          <button
            onClick={() => setBookmarkedOnly((v) => !v)}
            aria-pressed={bookmarkedOnly}
            className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition ${
              bookmarkedOnly
                ? "bg-gold-500 text-white hover:bg-gold-600"
                : "border border-brand-200 text-brand-700 dark:text-brand-300 hover:bg-brand-50"
            }`}
          >
            <FiStar className={`h-4 w-4 ${bookmarkedOnly ? "fill-white" : ""}`} />
            {bookmarkedOnly ? "Bookmarked" : "Bookmarked only"}
          </button>
        </div>
      )}

      <div className="mt-4 space-y-4">
        {lectures.length === 0 ? (
          <ComingSoon title="Lectures coming soon" message="Video lectures for this chapter will appear here." />
        ) : visibleLectures.length === 0 ? (
          <div className="rounded-card border border-dashed border-brand-200 bg-surface/60 p-10 text-center text-ink-soft">
            No bookmarked lectures in this chapter yet. Tap the ★ on a lecture to save it.
          </div>
        ) : (
          visibleLectures.map((lec) => (
            <LectureRow
              key={lec.id}
              lecture={lec}
              onPlay={setPlaying}
              saved={savedSet.has(lec.id)}
              done={doneSet.has(lec.id)}
              onToggleSave={toggleSave}
              onToggleDone={toggleDone}
            />
          ))
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
