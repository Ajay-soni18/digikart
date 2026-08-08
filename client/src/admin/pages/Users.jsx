import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";

const PAGE_SIZE = 20; // mirrors the backend DRF PAGE_SIZE

export default function Users() {
  const [data, setData] = useState(null);
  const [search, setSearch] = useState(""); // input text
  const [query, setQuery] = useState(""); // the term actually searched (submitted on Enter)
  const [page, setPage] = useState(1); // 1-indexed page of the paginated response
  const [error, setError] = useState(null);

  // Re-query when the submitted term OR the page changes — not on every keystroke.
  useEffect(() => {
    setError(null);
    setData(null);
    const params = { page, ...(query ? { search: query } : {}) };
    adminApi.users(params).then(setData).catch(() => setError("Could not load users."));
  }, [query, page]);

  // Submitting a new search resets to the first page of results.
  const submitSearch = () => {
    setPage(1);
    setQuery(search.trim());
  };

  const rows = Array.isArray(data) ? data : data?.results || [];
  const count = data?.count ?? rows.length;
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const hasPrev = Boolean(data?.previous) || page > 1;
  const hasNext = Boolean(data?.next);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Buyers</h1>
        <p className="text-sm text-ink-soft">{count} registered{count === 1 ? "" : ""}.</p>
      </div>

      <Input
        placeholder="Search by name or email… (press Enter)"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submitSearch()}
      />

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="overflow-hidden rounded-card bg-surface shadow-card ring-1 ring-brand-100/70">
        {!data && !error ? (
          <div className="flex justify-center py-12 text-brand-600 dark:text-brand-300"><Spinner /></div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-canvas text-ink-soft">
              <tr>
                <th className="px-4 py-3 font-semibold">Name</th>
                <th className="px-4 py-3 font-semibold">Email</th>
                <th className="px-4 py-3 font-semibold">Joined</th>
                <th className="px-4 py-3 font-semibold">Role</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-50">
              {rows.map((u) => (
                <tr key={u.id} className="hover:bg-brand-50/40">
                  <td className="px-4 py-3 font-medium text-ink">{u.full_name || "—"}</td>
                  <td className="px-4 py-3 text-ink-soft">{u.email}</td>
                  <td className="px-4 py-3 text-ink-soft">
                    {new Date(u.date_joined).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {u.is_staff ? (
                      <span className="rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-semibold text-brand-700 dark:text-brand-300">Admin</span>
                    ) : (
                      <span className="text-ink-soft">Student</span>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-ink-soft">
                    No students found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {count > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-ink-soft">
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!hasPrev}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasNext}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
