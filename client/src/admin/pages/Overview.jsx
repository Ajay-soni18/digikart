import { useEffect, useState } from "react";
import {
  FiUsers, FiBookOpen, FiFileText, FiVideo, FiAward, FiShoppingCart, FiTrendingUp,
} from "react-icons/fi";
import { adminApi } from "../adminApi";
import { Spinner } from "../../components/ui/Spinner";

const CARDS = [
  { key: "revenue", label: "Revenue", Icon: FiTrendingUp, tone: "bg-gold-100 text-gold-600 dark:text-gold-300", money: true },
  { key: "orders", label: "Paid orders", Icon: FiShoppingCart, tone: "bg-teal-100 text-teal-600 dark:text-teal-300" },
  { key: "users", label: "Buyers", Icon: FiUsers, tone: "bg-brand-100 text-brand-600 dark:text-brand-300" },
  { key: "categories", label: "Categories", Icon: FiBookOpen, tone: "bg-navy-100 text-navy-600" },
  { key: "products", label: "Products", Icon: FiFileText, tone: "bg-gold-100 text-gold-600 dark:text-gold-300" },
  { key: "files", label: "Files", Icon: FiVideo, tone: "bg-brand-100 text-brand-600 dark:text-brand-300" },
  { key: "bundles", label: "Bundles", Icon: FiAward, tone: "bg-teal-100 text-teal-600 dark:text-teal-300" },
];

export default function Overview() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    adminApi.overview().then(setStats).catch(() => setError("Could not load stats."));
  }, []);

  const fmt = (c) => (c.money ? `₹${Number(stats[c.key] || 0).toLocaleString("en-IN")}` : stats[c.key] ?? 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Overview</h1>
        <p className="text-sm text-ink-soft">A quick snapshot of your library.</p>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!stats && !error ? (
        <div className="flex justify-center py-12 text-brand-600 dark:text-brand-300"><Spinner /></div>
      ) : stats ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {CARDS.map((c) => (
            <div key={c.key} className="rounded-card bg-surface p-5 shadow-card ring-1 ring-line">
              <span className={`grid h-10 w-10 place-items-center rounded-xl ${c.tone}`}>
                <c.Icon className="h-5 w-5" />
              </span>
              <div className="mt-3 text-3xl font-extrabold text-ink">{fmt(c)}</div>
              <div className="text-sm text-ink-soft">{c.label}</div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
