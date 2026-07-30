/*
 * Site footer — premium navy section. Social links use REAL brand icons
 * (react-icons/fa) for recognition, hovering to each platform's colour.
 * The tagline, owner name, and social channel links are all fixed (hardcoded
 * below). The legal pages linked here are admin-editable via SiteContent.
 */
import { Link } from "react-router";
import {
  FaYoutube,
  FaInstagram,
  FaTelegramPlane,
  FaHeadset,
  FaInfoCircle,
  FaUserShield,
  FaExclamationTriangle,
} from "react-icons/fa";

// Fixed footer copy (not admin-editable). Update it here if it changes.
const OWNER = "Digikart";
const TAGLINE =
  "A digital product mart — notes, files, videos, links and bundles, delivered instantly.";

// Social channel links are fixed (not admin-editable). Update a URL here if a
// channel ever moves.
const SOCIALS = [
  {
    href: "https://www.youtube.com/@digikart",
    label: "YouTube",
    Icon: FaYoutube,
    hover: "hover:text-[#ff0000]",
  },
  {
    href: "https://www.instagram.com/digikart",
    label: "Instagram",
    Icon: FaInstagram,
    hover: "hover:text-[#e1306c]",
  },
  {
    href: "https://t.me/digikart",
    label: "Telegram",
    Icon: FaTelegramPlane,
    hover: "hover:text-[#229ed9]",
  },
];

// Standalone info pages, each rendered from admin-editable SiteContent.
const LEGAL_LINKS = [
  { to: "/about", label: "About Us", Icon: FaInfoCircle },
  { to: "/privacy", label: "Privacy Policy", Icon: FaUserShield },
  { to: "/disclaimer", label: "Disclaimer", Icon: FaExclamationTriangle },
];

export function Footer() {
  return (
    <footer className="mt-16 bg-navy-800 text-navy-200">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-10 px-6 py-12 lg:grid-cols-4">
        {/* Brand */}
        <div className="col-span-2">
          <p className="text-lg font-extrabold text-white">
            Digi<span className="text-brand-300">kart</span>
          </p>
          <p className="mt-2 max-w-sm text-sm text-navy-300">{TAGLINE}</p>
          <p className="mt-3 text-sm font-medium text-navy-100">By {OWNER}</p>
        </div>

        {/* Follow */}
        <div>
          <p className="text-sm font-bold uppercase tracking-wide text-white">Follow</p>
          <ul className="mt-4 space-y-3">
            {SOCIALS.map(({ href, label, Icon, hover }) => (
              <li key={label}>
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`group inline-flex items-center gap-3 text-sm text-navy-200 transition-colors ${hover}`}
                >
                  <span className="grid h-9 w-9 place-items-center rounded-full bg-navy-700 text-current transition-colors group-hover:bg-navy-900">
                    <Icon className="h-4 w-4" />
                  </span>
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </div>

        {/* Support */}
        <div>
          <p className="text-sm font-bold uppercase tracking-wide text-white">Support</p>
          <ul className="mt-4 space-y-3 text-sm">
            <li>
              <Link
                to="/contact"
                className="inline-flex items-center gap-2.5 text-navy-200 transition-colors hover:text-brand-300"
              >
                <FaHeadset className="h-4 w-4 shrink-0" />
                Help &amp; Contact
              </Link>
            </li>
            {LEGAL_LINKS.map(({ to, label, Icon }) => (
              <li key={to}>
                <Link
                  to={to}
                  className="inline-flex items-center gap-2.5 text-navy-200 transition-colors hover:text-brand-300"
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="border-t border-navy-700 py-4 text-center text-xs text-navy-400">
        © {new Date().getFullYear()} Digikart · By {OWNER}
      </div>
    </footer>
  );
}
