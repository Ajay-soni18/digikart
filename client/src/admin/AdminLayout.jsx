/* Admin shell: premium navy sidebar + content outlet. Guarded by an admin route. */
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import {
  FiBarChart2, FiBookOpen, FiBell, FiMail, FiSliders, FiUsers, FiMenu, FiExternalLink, FiLogOut, FiTrendingUp, FiTag, FiFilm,
} from "react-icons/fi";
import { Logo } from "../components/Logo";
import { ThemeToggle } from "../components/ThemeToggle";
import { Button } from "../components/ui/Button";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/admin", end: true, label: "Overview", Icon: FiBarChart2 },
  { to: "/admin/revenue", label: "Revenue", Icon: FiTrendingUp },
  { to: "/admin/content", label: "Content", Icon: FiBookOpen },
  { to: "/admin/general-videos", label: "General Videos", Icon: FiFilm },
  { to: "/admin/coupons", label: "Coupons", Icon: FiTag },
  { to: "/admin/announcements", label: "Announcements", Icon: FiBell },
  { to: "/admin/messages", label: "Messages", Icon: FiMail },
  { to: "/admin/site", label: "Site content", Icon: FiSliders },
  { to: "/admin/users", label: "Students", Icon: FiUsers },
];

export default function AdminLayout() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/", { replace: true });
  };

  // Navy sidebar: high contrast, brand-highlighted active item.
  const linkCls = ({ isActive }) =>
    [
      "flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm font-medium transition",
      isActive ? "bg-brand-600 text-white shadow-soft" : "text-navy-200 hover:bg-navy-700 hover:text-white",
    ].join(" ");

  return (
    <div className="min-h-screen bg-canvas">
      {/* Top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-surface/85 px-4 py-3 backdrop-blur sm:px-6">
        <div className="flex items-center gap-3">
          <button
            className="rounded-lg p-1.5 text-ink-soft lg:hidden"
            onClick={() => setOpen((o) => !o)}
            aria-label="Toggle menu"
          >
            <FiMenu className="h-5 w-5" />
          </button>
          <Logo to="/admin" imgClassName="h-9 w-auto" />
          <span className="hidden rounded-full bg-navy-100 px-2.5 py-0.5 text-xs font-bold text-navy-700 sm:inline">
            Admin
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button variant="ghost" size="sm" icon={FiExternalLink} onClick={() => navigate("/dashboard")}>
            <span className="hidden sm:inline">View site</span>
          </Button>
          <Button variant="outline" size="sm" icon={FiLogOut} onClick={handleLogout}>
            <span className="hidden sm:inline">Logout</span>
          </Button>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6 sm:px-6">
        {/* Sidebar */}
        <aside className={`${open ? "block" : "hidden"} w-full shrink-0 lg:block lg:w-60`}>
          <nav className="space-y-1 rounded-card bg-navy-800 p-3 shadow-soft">
            {NAV.map(({ to, end, label, Icon }) => (
              <NavLink key={to} to={to} end={end} className={linkCls} onClick={() => setOpen(false)}>
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>
          <p className="mt-3 px-2 text-xs text-ink-soft">
            Signed in as<br />
            <span className="font-medium text-ink">{user?.email}</span>
          </p>
        </aside>

        {/* Main */}
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
