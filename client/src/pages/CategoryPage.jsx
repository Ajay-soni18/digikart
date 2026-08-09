/*
 * A category: breadcrumb, any sub-categories, the bundles sold here, and the
 * products themselves.
 *
 * Bundles are listed above products deliberately — a bundle is usually the
 * cheaper route to the same things, and burying it under a wall of individual
 * items just costs the buyer money.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { FiArrowRight, FiCheck, FiFolder, FiLock, FiPlay, FiShoppingCart, FiX } from "react-icons/fi";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { ComingSoonBadge } from "../components/ComingSoon";
import { Spinner } from "../components/ui/Spinner";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { useCart } from "../cart/CartContext";
import { catalogApi } from "../lib/catalogApi";
import { money } from "../lib/pricing";
import { productRowState } from "../cart/cartItems";

function BundleCard({ bundle, inCart, onToggle }) {
  return (
    <div className="rounded-card border border-brand-200 bg-brand-50/60 p-5 dark:bg-brand-900/10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-ink">{bundle.title}</span>
            {bundle.is_coming_soon && <ComingSoonBadge />}
          </div>
          <p className="mt-1 text-sm text-muted">
            {bundle.product_count} item{bundle.product_count === 1 ? "" : "s"} included
            {bundle.description ? ` · ${bundle.description}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-lg font-extrabold text-ink">{money(bundle.price)}</span>
          {bundle.unlocked ? (
            <span className="inline-flex items-center gap-1 text-sm font-semibold text-emerald-600">
              <FiCheck className="h-4 w-4" /> Owned
            </span>
          ) : bundle.purchasable === false ? (
            // Empty, or holding only free items — checkout would reject a ₹0
            // total, so don't offer a button that can only fail.
            <span className="text-sm text-muted">Nothing to buy yet</span>
          ) : (
            <Button
              size="sm"
              variant={inCart ? "secondary" : "primary"}
              disabled={bundle.is_coming_soon}
              onClick={() => onToggle(bundle)}
              title={inCart ? "Remove from cart" : "Add to cart"}
            >
              {inCart ? <><FiX className="h-4 w-4" /> Remove</> : "Add bundle"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProductRow({ product, state, inCart, onToggle, onOpen }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-brand-100 bg-surface p-4">
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
        disabled={state === "coming_soon"}
        onClick={() => state !== "coming_soon" && onOpen(product)}
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-600 dark:text-brand-300">
          {product.youtube_video_id ? <FiPlay className="h-4 w-4" /> : <FiFolder className="h-4 w-4" />}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-semibold text-ink">{product.title}</span>
          <span className="block text-xs text-muted">
            {product.file_count} file{product.file_count === 1 ? "" : "s"}
            {product.is_free ? " · Free" : ""}
          </span>
        </span>
      </button>

      <div className="flex items-center gap-3">
        {state === "coming_soon" && <ComingSoonBadge />}
        {state === "owned" && (
          <span className="inline-flex items-center gap-1 text-sm font-semibold text-emerald-600">
            <FiCheck className="h-4 w-4" /> Owned
          </span>
        )}
        {state === "free" && !product.unlocked && (
          <span className="text-sm font-semibold text-brand-700 dark:text-brand-300">Free</span>
        )}
        {state === "covered" && (
          <span className="inline-flex items-center gap-1 text-sm text-muted">
            <FiCheck className="h-4 w-4" /> In your bundle
          </span>
        )}
        {state === "buyable" && (
          <>
            <span className="font-bold text-ink">{money(product.price)}</span>
            <Button
              size="sm"
              variant={inCart ? "secondary" : "primary"}
              onClick={() => onToggle(product)}
              title={inCart ? "Remove from cart" : "Add to cart"}
            >
              {inCart ? <><FiX className="h-4 w-4" /> Remove</> : <><FiShoppingCart className="h-4 w-4" /> Add</>}
            </Button>
          </>
        )}
        {!product.unlocked && state !== "free" && state !== "buyable" && state !== "covered" && (
          <FiLock className="h-4 w-4 text-muted" />
        )}
      </div>
    </div>
  );
}

export default function CategoryPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { toggle, has, purchaseVersion } = useCart();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    catalogApi
      .category(slug)
      .then(setData)
      .catch(() => setError("That category could not be loaded."));
  }, [slug, purchaseVersion]);

  // A product is "covered" when a bundle already in the cart contains it. The
  // server enforces this too; here it just stops us offering a pointless
  // second purchase.
  const coveredIds = useMemo(() => {
    const covered = new Set();
    for (const bundle of data?.bundles || []) {
      if (!has("bundle", bundle.id)) continue;
      for (const product of data?.products || []) covered.add(product.id);
    }
    return covered;
  }, [data, has]);

  if (error) {
    return (
      <div className="flex min-h-screen flex-col bg-canvas">
        <AppHeader />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
          <Alert>{error}</Alert>
        </main>
        <Footer />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex min-h-screen flex-col bg-canvas">
        <AppHeader />
        <main className="flex flex-1 justify-center py-24 text-brand-600 dark:text-brand-300">
          <Spinner className="h-9 w-9" />
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <nav className="flex flex-wrap items-center gap-1 text-xs text-muted">
          <Link to="/dashboard" className="hover:text-ink">Catalog</Link>
          {data.breadcrumb.map((crumb) => (
            <span key={crumb.slug} className="flex items-center gap-1">
              <span>/</span>
              <Link to={`/c/${crumb.slug}`} className="hover:text-ink">{crumb.name}</Link>
            </span>
          ))}
        </nav>

        <div className="mt-2 flex items-center gap-2">
          <h1 className="text-2xl font-extrabold text-ink">{data.name}</h1>
          {data.is_coming_soon && <ComingSoonBadge />}
        </div>
        {data.description && <p className="mt-1 text-sm text-muted">{data.description}</p>}

        {data.children.length > 0 && (
          <section className="mt-8">
            <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Browse</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.children.map((child) => (
                <Link
                  key={child.id}
                  to={`/c/${child.slug}`}
                  className="group flex items-center justify-between gap-3 rounded-card border border-brand-100 bg-surface p-4 transition hover:-translate-y-0.5 hover:shadow-lift"
                >
                  <span>
                    <span className="block font-semibold text-ink">{child.name}</span>
                    <span className="text-xs text-muted">{child.product_count} items</span>
                  </span>
                  <FiArrowRight className="h-4 w-4 text-brand-600 transition-all group-hover:translate-x-0.5 dark:text-brand-300" />
                </Link>
              ))}
            </div>
          </section>
        )}

        {data.bundles.length > 0 && (
          <section className="mt-8">
            <h2 className="text-sm font-bold uppercase tracking-wide text-muted">
              Buy together and save
            </h2>
            <div className="mt-3 space-y-3">
              {data.bundles.map((bundle) => (
                <BundleCard
                  key={bundle.id}
                  bundle={bundle}
                  inCart={has("bundle", bundle.id)}
                  onToggle={(b) => toggle("bundle", b.id)}
                />
              ))}
            </div>
          </section>
        )}

        {data.products.length > 0 && (
          <section className="mt-8">
            <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Items</h2>
            <div className="mt-3 space-y-2">
              {data.products.map((product) => (
                <ProductRow
                  key={product.id}
                  product={product}
                  state={productRowState(product, {
                    coveringBundleInCart: coveredIds.has(product.id),
                  })}
                  inCart={has("product", product.id)}
                  onToggle={(p) => toggle("product", p.id)}
                  onOpen={(p) => navigate(`/p/${p.slug}`)}
                />
              ))}
            </div>
          </section>
        )}

        {data.children.length === 0 &&
          data.products.length === 0 &&
          data.bundles.length === 0 && (
            <p className="mt-10 text-sm text-muted">Nothing here yet.</p>
          )}
      </main>
      <Footer />
    </div>
  );
}
