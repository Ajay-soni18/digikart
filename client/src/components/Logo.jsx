/* Brand logo. Uses the uploaded mark from /public. */
import { Link } from "react-router";

const LOGO_SRC = "/digikart-logo.png";

export function Logo({ to = "/", className = "", imgClassName = "h-12 w-auto" }) {
  return (
    // shrink-0: never let a cramped flex row (e.g. the mobile navbar) squeeze the
    // logo — other items yield first. The image keeps its aspect ratio via
    // object-contain + max-w-none so it's never stretched, cropped, or compressed.
    <Link to={to} className={`inline-flex shrink-0 items-center ${className}`} aria-label="Digikart — home">
      <img
        src={LOGO_SRC}
        alt="Digikart"
        className={`block max-w-none object-contain ${imgClassName} rounded-xl`}
      />
    </Link>
  );
}
