/*
 * A product page: the free YouTube hook (if any), the files it includes, and
 * the ways to buy it.
 *
 * The video plays for everyone, signed in or not — YouTube URLs can't be
 * access-gated, so pretending otherwise would be theatre. The files are what's
 * actually protected: a locked product shows their names and sizes but no way
 * to reach the bytes.
 */
import { Suspense, lazy, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { FiCheck, FiDownload, FiEye, FiLock, FiShoppingCart } from "react-icons/fi";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { ComingSoonBadge } from "../components/ComingSoon";
import { FullScreenLoader, Spinner } from "../components/ui/Spinner";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { useCart } from "../cart/CartContext";
import { catalogApi } from "../lib/catalogApi";
import { money } from "../lib/pricing";
import { api } from "../lib/api";

// The viewer drags in pdf.js (~250 kB). Most visits to a product page never
// open it, so it loads only when someone actually reads a protected file.
const FileViewer = lazy(() =>
  import("./FileViewer").then((m) => ({ default: m.FileViewer }))
);

const SIZES = ["B", "KB", "MB", "GB"];

function humanSize(bytes) {
  if (!bytes) return "";
  let value = Number(bytes);
  let unit = 0;
  while (value >= 1024 && unit < SIZES.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${SIZES[unit]}`;
}

function FileRow({ file, unlocked, onOpen }) {
  const protectedView = file.delivery === "protected";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-brand-100 bg-surface p-4">
      <div className="min-w-0">
        <span className="block truncate font-semibold text-ink">{file.title}</span>
        <span className="text-xs text-muted">
          {file.file_type.toUpperCase()}
          {file.page_count ? ` · ${file.page_count} pages` : ""}
          {file.size_bytes ? ` · ${humanSize(file.size_bytes)}` : ""}
        </span>
      </div>
      {unlocked ? (
        <Button size="sm" variant="secondary" onClick={() => onOpen(file)}>
          {protectedView ? (
            <><FiEye className="h-4 w-4" /> Read</>
          ) : (
            <><FiDownload className="h-4 w-4" /> Download</>
          )}
        </Button>
      ) : (
        <span className="inline-flex items-center gap-1 text-sm text-muted">
          <FiLock className="h-4 w-4" /> Locked
        </span>
      )}
    </div>
  );
}

export default function ProductPage() {
  const { slug } = useParams();
  const { add, has, purchaseVersion } = useCart();
  const [product, setProduct] = useState(null);
  const [error, setError] = useState(null);
  const [reading, setReading] = useState(null); // a protected file being viewed

  useEffect(() => {
    setProduct(null);
    setError(null);
    catalogApi
      .product(slug)
      .then(setProduct)
      .catch(() => setError("That product could not be loaded."));
  }, [slug, purchaseVersion]);

  const openFile = async (file) => {
    if (file.delivery === "protected") {
      setReading(file);
      return;
    }
    // Plain download: ask for a signed URL and hand it to the browser. The URL
    // is short-lived, so it's fetched at click time rather than page load.
    try {
      const { data } = await api.get(`/files/${file.id}/signed-url/`);
      window.open(data.original.url, "_blank", "noopener");
    } catch {
      setError("That download link could not be created. Please try again.");
    }
  };

  if (error && !product) {
    return (
      <div className="flex min-h-screen flex-col bg-canvas">
        <AppHeader />
        <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
          <Alert>{error}</Alert>
        </main>
        <Footer />
      </div>
    );
  }

  if (!product) {
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

  if (reading) {
    return (
      <Suspense fallback={<FullScreenLoader label="Opening…" />}>
        <FileViewer
          file={reading}
          productId={product.id}
          title={product.title}
          onClose={() => setReading(null)}
        />
      </Suspense>
    );
  }

  const inCart = has("product", product.id);

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8 sm:px-6">
        <nav className="text-xs text-muted">
          <Link to="/dashboard" className="hover:text-ink">Catalog</Link>
          <span> / </span>
          <Link to={`/c/${product.category.slug}`} className="hover:text-ink">
            {product.category.path}
          </Link>
        </nav>

        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-extrabold text-ink">{product.title}</h1>
              {product.is_coming_soon && <ComingSoonBadge />}
            </div>
            {product.description && (
              <p className="mt-2 max-w-2xl text-sm text-muted">{product.description}</p>
            )}
          </div>

          <div className="flex items-center gap-3">
            {product.unlocked ? (
              <span className="inline-flex items-center gap-1 font-semibold text-emerald-600">
                <FiCheck className="h-5 w-5" /> Yours
              </span>
            ) : product.is_free ? (
              <span className="font-semibold text-brand-700 dark:text-brand-300">
                Free — sign in to open
              </span>
            ) : product.purchasable ? (
              <>
                <span className="text-xl font-extrabold text-ink">{money(product.price)}</span>
                <Button
                  variant={inCart ? "secondary" : "primary"}
                  disabled={inCart || product.is_coming_soon}
                  onClick={() => add("product", product.id)}
                >
                  {inCart ? "In cart" : <><FiShoppingCart className="h-4 w-4" /> Add to cart</>}
                </Button>
              </>
            ) : (
              <span className="text-sm text-muted">Sold as part of a bundle</span>
            )}
          </div>
        </div>

        {product.youtube_video_id && (
          <section className="mt-8">
            <div className="aspect-video w-full overflow-hidden rounded-card border border-brand-100 bg-black">
              <iframe
                className="h-full w-full"
                src={`https://www.youtube.com/embed/${product.youtube_video_id}`}
                title={product.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
            <p className="mt-2 text-xs text-muted">
              The video is free to watch. The files below are included with your purchase.
            </p>
          </section>
        )}

        {product.files.length > 0 && (
          <section className="mt-8">
            <h2 className="text-sm font-bold uppercase tracking-wide text-muted">
              {product.files.length} file{product.files.length === 1 ? "" : "s"} included
            </h2>
            <div className="mt-3 space-y-2">
              {product.files.map((file) => (
                <FileRow
                  key={file.id}
                  file={file}
                  unlocked={product.unlocked}
                  onOpen={openFile}
                />
              ))}
            </div>
          </section>
        )}

        {product.in_bundles.length > 0 && !product.unlocked && (
          <section className="mt-8">
            <h2 className="text-sm font-bold uppercase tracking-wide text-muted">
              Also available in
            </h2>
            <div className="mt-3 space-y-3">
              {product.in_bundles.map((bundle) => (
                <div
                  key={bundle.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-brand-200 bg-brand-50/60 p-4 dark:bg-brand-900/10"
                >
                  <div>
                    <span className="block font-semibold text-ink">{bundle.title}</span>
                    <span className="text-xs text-muted">
                      {bundle.product_count} items included
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-ink">{money(bundle.price)}</span>
                    <Button
                      size="sm"
                      variant={has("bundle", bundle.id) ? "secondary" : "primary"}
                      disabled={has("bundle", bundle.id)}
                      onClick={() => add("bundle", bundle.id)}
                    >
                      {has("bundle", bundle.id) ? "In cart" : "Add bundle"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {error && <Alert className="mt-6">{error}</Alert>}
      </main>
      <Footer />
    </div>
  );
}
