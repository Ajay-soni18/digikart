/*
 * Bundle admin: the bundles themselves, and what each one contains.
 *
 * Membership is resolved live, so adding a product here immediately grants it
 * to everyone who has already bought the bundle. That is intended — it's how a
 * "everything in this set, forever" purchase keeps its promise — but it does
 * mean adding something is a decision about past buyers, not just future ones.
 */
import { useState } from "react";
import { CrudPanel } from "../CrudPanel";
import { Alert } from "../../components/ui/Alert";

export default function Bundles() {
  const [bundle, setBundle] = useState(null);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-ink">Bundles</h1>
        <p className="mt-1 text-sm text-muted">
          A bundle sells a set of products together, and can nest other bundles.
          Anything you add later reaches everyone who already bought it.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <CrudPanel
          title="Bundles"
          resource="bundles"
          onOpen={setBundle}
          itemLabel={(it) => it.title}
          renderBadges={(it) => `₹${it.price} · ${it.product_count} products`}
          addLabel="New bundle"
          selectable
          supportsComingSoon
        />

        {bundle ? (
          <CrudPanel
            title={`Contents · ${bundle.title}`}
            resource="bundle-items"
            params={{ bundle: bundle.id }}
            parentDefaults={{ bundle: bundle.id }}
            itemLabel={(it) => it.label}
            renderBadges={(it) => it.kind}
            addLabel="Add item"
          />
        ) : (
          <Alert tone="info">Pick a bundle to manage what it contains.</Alert>
        )}
      </div>
    </div>
  );
}
