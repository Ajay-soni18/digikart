/*
 * Admin "Revenue & Transactions" — revenue analytics (total + today/month/year,
 * subject/unit/chapter breakdowns) and a full transaction log with Razorpay
 * status, user details and date/time, so the admin can audit who paid and
 * which payments succeeded vs failed. Everything is date-range filterable.
 */
import { useEffect, useMemo, useState } from "react";
import {
  FiTrendingUp, FiCalendar, FiCheckCircle, FiXCircle, FiClock, FiSearch,
} from "react-icons/fi";
import { adminApi } from "../adminApi";
import { Spinner } from "../../components/ui/Spinner";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/fields";

const money = (v) => `₹${Number(v || 0).toLocaleString("en-IN")}`;
const dateTime = (s) => (s ? new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");

const STATUS_BADGE = {
  paid: "bg-teal-100 text-teal-700 dark:text-teal-300",
  failed: "bg-red-100 text-red-700 dark:text-red-300",
  created: "bg-navy-100 text-navy-600",
};

function StatCard({ Icon, tone, label, value }) {
  return (
    <div className="rounded-card bg-surface p-5 shadow-card ring-1 ring-line">
      <span className={`grid h-10 w-10 place-items-center rounded-xl ${tone}`}>
        <Icon className="h-5 w-5" />
      </span>
      <div className="mt-3 text-2xl font-extrabold text-ink">{value}</div>
      <div className="text-sm text-ink-soft">{label}</div>
    </div>
  );
}

function BarList({ rows, emptyText }) {
  if (!rows?.length) return <p className="py-6 text-center text-sm text-ink-soft">{emptyText}</p>;
  const max = Math.max(...rows.map((r) => Number(r.revenue)), 1);
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.id ?? r.name}>
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate font-medium text-ink">{r.name}</span>
            <span className="flex-shrink-0 font-semibold text-gold-700 dark:text-gold-300">{money(r.revenue)}</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-canvas-2">
            <div className="h-full rounded-full bg-brand-400" style={{ width: `${(Number(r.revenue) / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function Revenue() {
  const [range, setRange] = useState({ from: "", to: "" });
  const [rev, setRev] = useState(null);
  const [revError, setRevError] = useState(null);
  const [tab, setTab] = useState("by_subject");

  // Transactions
  const [txnFilters, setTxnFilters] = useState({ status: "", search: "" });
  const [searchInput, setSearchInput] = useState(""); // search box text; applied on Enter
  const [page, setPage] = useState(1);
  const [txns, setTxns] = useState(null);

  // Load revenue analytics when the date range changes.
  useEffect(() => {
    setRev(null);
    setRevError(null);
    const params = {};
    if (range.from) params.from = range.from;
    if (range.to) params.to = range.to;
    adminApi.revenue(params).then(setRev).catch(() => setRevError("Could not load revenue."));
  }, [range]);

  // Load transactions when filters/range/page change. The free-text search only
  // changes txnFilters.search on Enter, so we never query on every keystroke.
  useEffect(() => {
    const params = { page };
    if (txnFilters.status) params.status = txnFilters.status;
    if (txnFilters.search) params.search = txnFilters.search;
    if (range.from) params.from = range.from;
    if (range.to) params.to = range.to;
    adminApi.transactions(params).then(setTxns).catch(() => setTxns({ results: [], count: 0 }));
  }, [txnFilters, range, page]);

  // Reset to page 1 whenever a filter changes.
  useEffect(() => setPage(1), [txnFilters, range]);

  const s = rev?.summary;
  const tabRows = rev?.[tab] || [];
  const rows = txns?.results || [];
  const pageSize = 20;
  const totalPages = txns ? Math.max(1, Math.ceil((txns.count || 0) / pageSize)) : 1;

  const TABS = useMemo(() => ([
    { key: "by_subject", label: "By subject" },
    { key: "by_unit", label: "By unit" },
    { key: "by_chapter", label: "By chapter" },
  ]), []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">Revenue &amp; Transactions</h1>
          <p className="text-sm text-ink-soft">Track earnings and audit every payment.</p>
        </div>
        {/* Date range filter (applies to revenue + transactions) */}
        <div className="flex items-end gap-2">
          <label className="text-xs font-medium text-ink-soft">
            From
            <input type="date" value={range.from}
              onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))}
              className="mt-1 block rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm text-ink focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400/40" />
          </label>
          <label className="text-xs font-medium text-ink-soft">
            To
            <input type="date" value={range.to}
              onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))}
              className="mt-1 block rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm text-ink focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400/40" />
          </label>
          {(range.from || range.to) && (
            <button onClick={() => setRange({ from: "", to: "" })} className="pb-2 text-xs font-semibold text-brand-700 dark:text-brand-300 hover:underline">
              Clear
            </button>
          )}
        </div>
      </div>

      {revError && <p className="text-sm text-red-600 dark:text-red-400">{revError}</p>}

      {/* Summary */}
      {!rev && !revError ? (
        <div className="flex justify-center py-12 text-brand-600 dark:text-brand-300"><Spinner /></div>
      ) : s ? (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard Icon={FiTrendingUp} tone="bg-gold-100 text-gold-600 dark:text-gold-300"
              label={range.from || range.to ? "Revenue (range)" : "Total revenue"} value={money(s.total_revenue)} />
            <StatCard Icon={FiCalendar} tone="bg-teal-100 text-teal-600 dark:text-teal-300" label="Today" value={money(s.today)} />
            <StatCard Icon={FiCalendar} tone="bg-brand-100 text-brand-600 dark:text-brand-300" label="This month" value={money(s.this_month)} />
            <StatCard Icon={FiCalendar} tone="bg-navy-100 text-navy-600" label="This year" value={money(s.this_year)} />
            <StatCard Icon={FiCheckCircle} tone="bg-teal-100 text-teal-600 dark:text-teal-300" label="Paid orders" value={s.paid_count} />
            <StatCard Icon={FiXCircle} tone="bg-red-100 text-red-600 dark:text-red-400" label="Failed" value={s.failed_count} />
            <StatCard Icon={FiClock} tone="bg-navy-100 text-navy-600" label="Pending" value={s.pending_count} />
          </div>

          {/* Breakdown + monthly trend */}
          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-card bg-surface p-5 shadow-card ring-1 ring-line">
              <div className="mb-4 flex flex-wrap gap-2">
                {TABS.map((t) => (
                  <button key={t.key} onClick={() => setTab(t.key)}
                    className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition ${
                      tab === t.key ? "bg-brand-600 text-white" : "bg-canvas-2 text-ink-soft hover:text-brand-700 dark:hover:text-brand-300"
                    }`}>
                    {t.label}
                  </button>
                ))}
              </div>
              <BarList rows={tabRows} emptyText="No revenue in this range yet." />
            </section>

            <section className="rounded-card bg-surface p-5 shadow-card ring-1 ring-line">
              <h3 className="mb-4 text-base font-bold text-ink">Monthly revenue</h3>
              <BarList
                rows={(rev.monthly || []).map((m) => ({ id: m.month, name: m.month, revenue: m.revenue }))}
                emptyText="No revenue in this range yet."
              />
            </section>
          </div>
        </>
      ) : null}

      {/* Transactions */}
      <section className="rounded-card bg-surface shadow-card ring-1 ring-line">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h3 className="text-base font-bold text-ink">Transactions</h3>
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-40">
              <Select
                value={txnFilters.status}
                onChange={(e) => setTxnFilters((f) => ({ ...f, status: e.target.value }))}
                options={[
                  { value: "", label: "All statuses" },
                  { value: "paid", label: "Paid" },
                  { value: "failed", label: "Failed" },
                  { value: "created", label: "Pending" },
                ]}
              />
            </div>
            <div className="relative">
              <FiSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && setTxnFilters((f) => ({ ...f, search: searchInput.trim() }))}
                placeholder="Email, name, payment id… (press Enter)"
                className="w-56 rounded-xl border border-line-strong bg-surface py-2 pl-9 pr-3 text-sm text-ink focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-400/40"
              />
            </div>
          </div>
        </div>

        {!txns ? (
          <div className="flex justify-center py-12 text-brand-600 dark:text-brand-300"><Spinner /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-canvas text-ink-soft">
                <tr>
                  <th className="px-4 py-3 font-semibold">Date &amp; time</th>
                  <th className="px-4 py-3 font-semibold">Student</th>
                  <th className="px-4 py-3 font-semibold">Items</th>
                  <th className="px-4 py-3 font-semibold">Amount</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((t) => (
                  <tr key={t.id} className="align-top hover:bg-brand-50/40">
                    <td className="whitespace-nowrap px-4 py-3 text-ink-soft">
                      {dateTime(t.paid_at || t.created_at)}
                      {t.razorpay_payment_id && (
                        <div className="text-xs text-ink-soft/70">{t.razorpay_payment_id}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-ink">{t.user?.name || "—"}</div>
                      <div className="text-xs text-ink-soft">{t.user?.email}</div>
                    </td>
                    <td className="px-4 py-3 text-ink-soft">
                      {t.items.map((it, i) => <div key={i}>{it.label}</div>)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-ink">{money(t.amount)}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${STATUS_BADGE[t.status]}`}>
                        {t.status === "created" ? "pending" : t.status}
                      </span>
                      {t.is_mock && <span className="ml-1 rounded-full bg-navy-100 px-2 py-0.5 text-[10px] font-bold text-navy-500">TEST</span>}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-10 text-center text-ink-soft">No transactions found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {txns && txns.count > pageSize && (
          <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
            <span className="text-ink-soft">{txns.count} transactions · page {page} of {totalPages}</span>
            <div className="flex gap-2">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
                className="rounded-full px-3 py-1 font-semibold text-brand-700 dark:text-brand-300 disabled:opacity-40">Prev</button>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}
                className="rounded-full px-3 py-1 font-semibold text-brand-700 dark:text-brand-300 disabled:opacity-40">Next</button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
