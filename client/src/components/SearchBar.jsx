/*
 * Global search for the top bar — finds years, subjects, units and chapters.
 * Fires only when the user presses Enter, a results dropdown, keyboard-dismiss,
 * and click-to-navigate.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { FiSearch, FiAward, FiBookOpen, FiFolder, FiFileText } from "react-icons/fi";
import { contentApi } from "../lib/contentApi";
import { Spinner } from "./ui/Spinner";

const TYPE_META = {
  year: { Icon: FiAward, tone: "bg-navy-100 text-navy-600" },
  subject: { Icon: FiBookOpen, tone: "bg-brand-100 text-brand-700 dark:text-brand-300" },
  unit: { Icon: FiFolder, tone: "bg-teal-100 text-teal-700 dark:text-teal-300" },
  chapter: { Icon: FiFileText, tone: "bg-gold-100 text-gold-700 dark:text-gold-300" },
};

function destination(r) {
  if (r.type === "subject" || r.type === "unit") return `/subjects/${r.subject_slug}`;
  if (r.type === "chapter") return `/subjects/${r.subject_slug}/chapters/${r.chapter_id}/notes`;
  return "/dashboard"; // years have no dedicated page
}

export function SearchBar() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [searched, setSearched] = useState(""); // the query actually run
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef(null);

  // Run the search only when the user presses Enter — never on every keystroke.
  const runSearch = () => {
    const term = q.trim();
    if (term.length < 2) return;
    setSearched(term);
    setOpen(true);
    setLoading(true);
    contentApi
      .search(term)
      .then((d) => setResults(d.results || []))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  };

  // Close on outside click
  useEffect(() => {
    const onClick = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const goTo = (r) => {
    setOpen(false);
    setQ("");
    setSearched("");
    setResults([]);
    navigate(destination(r));
  };

  const showDropdown = open && searched.length >= 2;

  return (
    <div ref={boxRef} className="relative w-full max-w-md">
      <div className="relative">
        <FiSearch className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            else if (e.key === "Enter") runSearch();
          }}
          placeholder="Search subjects, units, chapters… (press Enter)"
          aria-label="Search content"
          className="w-full rounded-full border border-line-strong bg-surface py-2 pl-10 pr-3 text-sm text-ink placeholder:text-ink-soft/70 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400/40"
        />
      </div>

      {showDropdown && (
        <div className="absolute z-40 mt-2 w-full overflow-hidden rounded-2xl border border-brand-100 bg-surface shadow-lift">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-ink-soft">
              <Spinner className="h-4 w-4" /> Searching…
            </div>
          ) : results.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-ink-soft">No matches for “{searched}”.</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto py-1">
              {results.map((r, i) => {
                const meta = TYPE_META[r.type] || TYPE_META.chapter;
                return (
                  <li key={`${r.type}-${i}`}>
                    <button
                      onClick={() => goTo(r)}
                      className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-brand-50"
                    >
                      <span className={`grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg ${meta.tone}`}>
                        <meta.Icon className="h-4 w-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-ink">{r.label}</span>
                        <span className="block truncate text-xs text-ink-soft">{r.sublabel}</span>
                      </span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${meta.tone}`}>
                        {r.type}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
