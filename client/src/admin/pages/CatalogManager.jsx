/*
 * Catalog admin: categories → products → files.
 *
 * A drill-down rather than a tree widget: pick a category, then a product, then
 * manage its files. Categories are listed flat by name with their parent path
 * underneath — easier to scan than an expandable tree once there are more than a
 * dozen, and far less code to get right.
 *
 * The panels only sit side by side once the viewport is genuinely wide. Three
 * columns next to the admin sidebar leaves each one about 300px, which is not
 * enough for a name, a badge and two buttons.
 */
import { useEffect, useState } from "react";
import { FiUploadCloud } from "react-icons/fi";
import { CrudPanel } from "../CrudPanel";
import { adminApi } from "../adminApi";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";

function FileUpload({ file, onUploaded }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const pick = async (event) => {
    const chosen = event.target.files?.[0];
    if (!chosen) return;
    setBusy(true);
    setError(null);
    try {
      await adminApi.uploadFile(file.id, chosen);
      onUploaded?.();
    } catch (e) {
      setError(e?.response?.data?.file || "Upload failed. Please try again.");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  };

  return (
    <div className="mt-1">
      <label className="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-brand-700 dark:text-brand-300">
        <FiUploadCloud className="h-4 w-4" />
        {busy ? "Uploading…" : file.file_version ? "Replace file" : "Upload file"}
        <input type="file" className="hidden" onChange={pick} disabled={busy} />
      </label>
      {error && <p className="mt-1 text-xs text-rose-600">{String(error)}</p>}
    </div>
  );
}

export default function CatalogManager() {
  const [category, setCategory] = useState(null);
  const [product, setProduct] = useState(null);
  const [fileToken, setFileToken] = useState(0);
  const [counts, setCounts] = useState(null);

  useEffect(() => {
    adminApi.catalogOverview().then(setCounts).catch(() => setCounts(null));
  }, [category, product, fileToken]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-ink">Catalog</h1>
        <p className="mt-1 text-sm text-muted">
          Categories organise the storefront. Products are what people buy, and each
          product holds one or more files.
          {counts && (
            <> {" "}Currently {counts.categories} categories, {counts.products} products,{" "}
            {counts.files} files.</>
          )}
        </p>
      </header>

      <div className="grid gap-6 xl:grid-cols-2 2xl:grid-cols-3">
        <CrudPanel
          title="Categories"
          resource="categories"
          onOpen={(item) => {
            setCategory(item);
            setProduct(null);
          }}
          itemLabel={(it) => it.name}
          itemSubLabel={(it) => {
            const parts = (it.path || "").split(" · ");
            return parts.length > 1 ? parts.slice(0, -1).join(" · ") : "top level";
          }}
          renderBadges={(it) => (it.product_count ? `${it.product_count} products` : null)}
          addLabel="New category"
          selectable
          supportsComingSoon
        />

        {category ? (
          <CrudPanel
            title={`Products · ${category.name}`}
            resource="products"
            params={{ category: category.id }}
            parentDefaults={{ category: category.id }}
            onOpen={setProduct}
            itemLabel={(it) => it.title}
            renderBadges={(it) => (it.is_free ? "Free" : `₹${it.price}`)}
            addLabel="New product"
            selectable
            supportsComingSoon
          />
        ) : (
          <Alert tone="info">Pick a category to manage its products.</Alert>
        )}

        {product ? (
          <div className="space-y-3">
            <CrudPanel
              title={`Files · ${product.title}`}
              resource="product-files"
              params={{ product: product.id }}
              parentDefaults={{ product: product.id }}
              itemLabel={(it) => it.title}
              renderBadges={(it) =>
                it.file_version ? it.delivery : "no file uploaded yet"
              }
              addLabel="New file"
              refreshToken={fileToken}
            />
            <div className="rounded-card border border-brand-100 bg-surface p-4">
              <p className="text-xs text-muted">
                Create the file row first, then upload its bytes here. Re-uploading
                replaces the file and invalidates every reader's cached copy.
              </p>
              {(product.files || []).map((file) => (
                <div key={file.id} className="mt-3 border-t border-brand-100 pt-3">
                  <span className="text-sm font-semibold text-ink">{file.title}</span>
                  <FileUpload file={file} onUploaded={() => setFileToken((n) => n + 1)} />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <Alert tone="info">Pick a product to manage its files.</Alert>
        )}
      </div>
    </div>
  );
}
