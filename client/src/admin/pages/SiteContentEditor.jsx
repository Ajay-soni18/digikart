/* Edit the legal/info pages (About / Privacy / Disclaimer) and the Help &
 * Contact copy — no code changes needed. */
import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";
import { ResourceForm } from "../ResourceForm";
import { Spinner } from "../../components/ui/Spinner";

const SITE_FIELDS = [
  { name: "about_us", label: "About Us page", type: "textarea", rows: 10, hint: "Shown on the /about page. Leave blank to show a placeholder." },
  { name: "privacy_policy", label: "Privacy Policy page", type: "textarea", rows: 10, hint: "Shown on the /privacy page." },
  { name: "disclaimer", label: "Disclaimer page", type: "textarea", rows: 10, hint: "Shown on the /disclaimer page." },
  { name: "help_text", label: "Help section text", type: "textarea", hint: "Shown on the Help & Contact page." },
  { name: "contact_email", label: "Contact email", type: "text" },
];

export default function SiteContentEditor() {
  const [content, setContent] = useState(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    adminApi.getSiteContent().then(setContent).catch(() => setError("Could not load."));
  }, []);

  const handleSave = async (payload) => {
    await adminApi.saveSiteContent(payload);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Site content</h1>
        <p className="text-sm text-ink-soft">
          Control the About / Privacy / Disclaimer pages and the Help &amp; Contact
          copy without touching code.
        </p>
      </div>

      {saved && (
        <div className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700 ring-1 ring-emerald-100">
          Saved ✓
        </div>
      )}
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="max-w-2xl rounded-card bg-surface p-6 shadow-card ring-1 ring-brand-100/70">
        {content ? (
          <ResourceForm
            fields={SITE_FIELDS}
            initial={content}
            onSubmit={handleSave}
            submitLabel="Save changes"
          />
        ) : (
          <div className="flex justify-center py-12 text-brand-600 dark:text-brand-300"><Spinner /></div>
        )}
      </div>
    </div>
  );
}
