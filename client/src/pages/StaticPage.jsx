/*
 * A simple admin-written info page (About Us / Privacy Policy / Disclaimer).
 * The body is plain text stored on the SiteContent singleton; the matching
 * field is passed in via `field`. Line breaks the admin types are preserved.
 * Public — reachable from the footer on any page.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Logo } from "../components/Logo";
import { Footer } from "../components/Footer";
import { Spinner } from "../components/ui/Spinner";
import { api } from "../lib/api";

export default function StaticPage({ title, field }) {
  const [content, setContent] = useState(null); // null = loading; "" = empty

  useEffect(() => {
    document.title = `${title} · Digikart`;
  }, [title]);

  useEffect(() => {
    setContent(null);
    api
      .get("/site-content/")
      .then((r) => setContent(r.data[field] || ""))
      .catch(() => setContent("")); // treat a failure as "not written yet"
  }, [field]);

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <Logo imgClassName="h-11 w-auto" />
        <Link to="/" className="text-sm font-medium text-brand-700 dark:text-brand-300 hover:underline">← Home</Link>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-6">
        <h1 className="text-3xl font-extrabold tracking-tight text-ink">{title}</h1>

        {content === null ? (
          <div className="flex justify-center py-20 text-brand-600 dark:text-brand-300"><Spinner className="h-9 w-9" /></div>
        ) : content ? (
          <div className="mt-6 whitespace-pre-line text-ink-soft leading-relaxed">{content}</div>
        ) : (
          <div className="mt-6 rounded-card border border-dashed border-brand-200 bg-surface/60 px-6 py-12 text-center text-ink-soft">
            This page hasn't been written yet. Please check back soon.
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
