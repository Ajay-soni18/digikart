/*
 * Student home: announcements, then the MBBS years with their subjects.
 * Coming-soon items are badged and inert. (Bookmarks live on their own
 * lecture/notes pages, not here.)
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { FiBookOpen, FiArrowRight } from "react-icons/fi";
import { AppHeader } from "../components/AppHeader";
import { AnnouncementBanner } from "../components/AnnouncementBanner";
import { Footer } from "../components/Footer";
import { ComingSoonBadge } from "../components/ComingSoon";
import { GeneralPlaylists } from "../components/GeneralPlaylists";
import { Spinner } from "../components/ui/Spinner";
import { Alert } from "../components/ui/Alert";
import { useAuth } from "../auth/AuthContext";
import { contentApi } from "../lib/contentApi";

function SubjectCard({ subject, onOpen }) {
  const soon = subject.is_coming_soon;
  return (
    <button
      type="button"
      disabled={soon}
      onClick={() => !soon && onOpen(subject)}
      className={[
        "group flex items-center justify-between gap-3 rounded-card border p-5 text-left transition",
        soon
          ? "cursor-default border-brand-100 bg-surface/50"
          : "cursor-pointer border-brand-100 bg-surface shadow-card hover:-translate-y-0.5 hover:shadow-lift",
      ].join(" ")}
    >
      <div>
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-ink">{subject.name}</span>
          {soon && <ComingSoonBadge />}
        </div>
        {!soon && (
          <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-brand-700 dark:text-brand-300 group-hover:gap-1.5">
            Open subject <FiArrowRight className="h-3.5 w-3.5 transition-all" />
          </span>
        )}
      </div>
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-100 text-brand-600 dark:text-brand-300">
        <FiBookOpen className="h-5 w-5" />
      </span>
    </button>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [years, setYears] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    document.title = "Dashboard · Digikart";
  }, []);

  useEffect(() => {
    contentApi.years().then(setYears).catch(() => setError("Could not load your library."));
  }, []);

  const openSubject = (s) => navigate(`/subjects/${s.slug}`);

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <div className="overflow-hidden rounded-card border border-brand-100 bg-aurora px-6 py-6 text-center shadow-soft sm:py-8">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
            Welcome, <span className="text-brand-700 dark:text-brand-300">{user?.full_name?.split(" ")[0] || "student"}</span> 👋
          </h1>
          <p className="mx-auto mt-1.5 max-w-md text-sm text-ink-soft sm:text-base">
            Pick a year to start learning.
          </p>
        </div>

        {/* Latest active announcement — hidden entirely when there are none. */}
        <AnnouncementBanner />

        <Alert tone="error" className="mt-8" action={error ? { label: "Retry", onClick: () => window.location.reload() } : undefined}>
          {error}
        </Alert>

        {/* Admin-created general video headings (e.g. "The Academic Edge"),
            rendered above the MBBS years. Self-fetching; hides when empty. */}
        <GeneralPlaylists />

        {!years && !error && <div className="flex justify-center py-20 text-brand-600 dark:text-brand-300"><Spinner className="h-9 w-9" /></div>}

        {years && (
          <div className="mt-8 space-y-10">
            {years.map((year) => (
              <section key={year.id}>
                <div className="mb-4 flex items-center gap-3">
                  <h2 className="text-xl font-bold text-ink">{year.title}</h2>
                  {year.is_coming_soon && <ComingSoonBadge />}
                </div>
                {year.is_coming_soon || year.subjects.length === 0 ? (
                  <div className="rounded-card border border-dashed border-brand-200 bg-surface/50 px-6 py-8 text-center text-sm text-ink-soft">
                    Content coming soon for {year.title}.
                  </div>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {year.subjects.map((s) => <SubjectCard key={s.id} subject={s} onOpen={openSubject} />)}
                  </div>
                )}
              </section>
            ))}
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
