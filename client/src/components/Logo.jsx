/* Brand mark.
 *
 * Deliberately typographic rather than an image: there is no Digikart logo yet,
 * and shipping someone else's mark is worse than shipping none. When a real
 * logo exists, drop it in /public and render an <img> here — every surface
 * (header, admin sidebar, auth screens, landing) goes through this one
 * component, so nothing else needs touching.
 */
import { Link } from "react-router";

// Rough visual parity with the image sizes callers used to pass, so existing
// `imgClassName` values still produce a sensibly-sized mark.
const SIZES = {
  "h-9": "text-xl",
  "h-10": "text-2xl",
  "h-11": "text-2xl",
  "h-12": "text-3xl",
  "h-14": "text-4xl",
};

function sizeClass(imgClassName) {
  const match = Object.keys(SIZES).find((key) => imgClassName.includes(key));
  return SIZES[match] || "text-2xl";
}

export function Logo({ to = "/", className = "", imgClassName = "h-12 w-auto" }) {
  return (
    // shrink-0: never let a cramped flex row (e.g. the mobile navbar) squeeze
    // the mark — other items yield first.
    <Link
      to={to}
      className={`inline-flex shrink-0 items-center ${className}`}
      aria-label="Digikart — home"
    >
      <span
        className={`font-extrabold leading-none tracking-tight text-ink ${sizeClass(imgClassName)}`}
      >
        Digi<span className="text-brand-600 dark:text-brand-300">kart</span>
      </span>
    </Link>
  );
}
