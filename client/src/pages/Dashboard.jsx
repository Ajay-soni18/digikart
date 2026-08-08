/*
 * Buyer home: announcements, then the top level of the catalog.
 *
 * The tree is fetched whole (it's small) and only its roots are rendered here;
 * drilling in happens on CategoryPage. Coming-soon nodes are badged and inert.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { FiArrowRight, FiGrid } from "react-icons/fi";
import { AppHeader } from "../components/AppHeader";
import { AnnouncementBanner } from "../components/AnnouncementBanner";
import { Footer } from "../components/Footer";
import { ComingSoonBadge } from "../components/ComingSoon";
import { Spinner } from "../components/ui/Spinner";
import { Alert } from "../components/ui/Alert";
import { useAuth } from "../auth/AuthContext";
import { catalogApi } from "../lib/catalogApi";

export function CategoryCard({ category, onOpen }) {
  const soon = category.is_coming_soon;
  const count = category.product_count || 0;
  return (
    <button
      type="button"
      disabled={soon}
      onClick={() => !soon && onOpen(category)}
      className={[
        "group flex items-center justify-between gap-3 rounded-card border p-5 text-left transition",
        soon
          ? "cursor-default border-brand-100 bg-surface/50"
          : "cursor-pointer border-brand-100 bg-surface shadow-card hover:-translate-y-0.5 hover:shadow-lift",
      ].join(" ")}
    >
      <div>
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-ink">{category.name}</span>
          {soon && <ComingSoonBadge />}
        </div>
        {!soon && (
          <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-brand-700 dark:text-brand-300 group-hover:gap-1.5">
            {count > 0 ? `Browse ${count} item${count === 1 ? "" : "s"}` : "Browse"}
            <FiArrowRight className="h-3.5 w-3.5 transition-all" />
          </span>
        )}
      </div>
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-100 text-brand-600 dark:text-brand-300">
        <FiGrid className="h-5 w-5" />
      </span>
    </button>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tree, setTree] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    catalogApi
      .tree()
      .then(setTree)
      .catch(() => setError("Could not load the catalog."));
  }, []);

  const open = (category) => navigate(`/c/${category.slug}`);

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-extrabold text-ink">
          Welcome{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-muted">Pick a category to start browsing.</p>

        <AnnouncementBanner />

        {error && <Alert className="mt-6">{error}</Alert>}

        {!tree && !error && (
          <div className="flex justify-center py-20 text-brand-600 dark:text-brand-300">
            <Spinner className="h-9 w-9" />
          </div>
        )}

        {tree && tree.length === 0 && (
          <p className="mt-10 text-sm text-muted">
            Nothing here yet — the catalog is still being set up.
          </p>
        )}

        {tree && tree.length > 0 && (
          <div className="mt-8 space-y-10">
            {tree.map((root) => (
              <section key={root.id}>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-ink">{root.name}</h2>
                  {root.is_coming_soon && <ComingSoonBadge />}
                </div>
                {root.description && (
                  <p className="mt-1 text-sm text-muted">{root.description}</p>
                )}

                {root.is_coming_soon || root.children.length === 0 ? (
                  root.product_count > 0 ? (
                    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <CategoryCard category={root} onOpen={open} />
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-muted">
                      Content coming soon for {root.name}.
                    </p>
                  )
                ) : (
                  <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {root.children.map((child) => (
                      <CategoryCard key={child.id} category={child} onOpen={open} />
                    ))}
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
