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
            onCreate={(payload) => adminApi.createProductWithAttachment(payload)}
            itemLabel={(it) => it.title}
            renderBadges={(it) =>
              `${it.is_free ? "Free" : `₹${it.price}`} · ${(it.files || []).length} file${
                (it.files || []).length === 1 ? "" : "s"
              }`
            }
            addLabel="New product"
            selectable
            supportsComingSoon
          />
        ) : (
          <Alert tone="info">
            Pick a category on the left to manage its products. You can attach the
            first file while creating a product — no need to come back here.
          </Alert>
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
              {/* Name the product. "Replace file" with no context is a question,
                  not an instruction — especially next to a list that used to
                  show every file in the catalog. */}
              <p className="text-sm font-semibold text-ink">
                Files for “{product.title}”
              </p>
              <p className="mt-1 text-xs text-muted">
                Re-uploading replaces the bytes and invalidates every reader's cached
                copy. A product's first file can be attached on the product form.
              </p>
              {(product.files || []).length === 0 && (
                <p className="mt-3 border-t border-brand-100 pt-3 text-xs text-muted">
                  This product has no files yet. Add one above, then upload its bytes here.
                </p>
              )}
              {(product.files || []).map((file) => (
                <div key={file.id} className="mt-3 border-t border-brand-100 pt-3">
                  <span className="text-sm font-semibold text-ink">{file.title}</span>
                  <FileUpload file={file} onUploaded={() => setFileToken((n) => n + 1)} />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <Alert tone="info">
            Pick a product to add more files or replace one. A product's first file
            can be attached on the product form itself.
          </Alert>
        )}
      </div>
    </div>
  );
}
