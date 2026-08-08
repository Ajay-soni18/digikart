/* Admin inbox for Help & Contact messages, with status updates. */
import { useEffect, useState } from "react";
import { adminApi } from "../adminApi";
import { Spinner } from "../../components/ui/Spinner";
import { Select } from "../../components/ui/fields";

const STATUS = [
  { value: "new", label: "New" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
];

export default function ContactInbox() {
  const [messages, setMessages] = useState(null);
  const [error, setError] = useState(null);

  const load = () =>
    adminApi
      .list("contact-messages")
      .then((d) => setMessages(Array.isArray(d) ? d : d.results || []))
      .catch(() => setError("Could not load messages."));

  useEffect(() => {
    load();
  }, []);

  const updateStatus = async (id, status) => {
    await adminApi.update("contact-messages", id, { status });
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Messages</h1>
        <p className="text-sm text-ink-soft">Questions and support requests from buyers.</p>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!messages && !error ? (
        <div className="flex justify-center py-12 text-brand-600 dark:text-brand-300"><Spinner /></div>
      ) : messages && messages.length === 0 ? (
        <p className="rounded-card bg-surface p-8 text-center text-ink-soft shadow-card ring-1 ring-brand-100/70">
          No messages yet.
        </p>
      ) : (
        <div className="space-y-3">
          {messages?.map((m) => (
            <div key={m.id} className="rounded-card bg-surface p-5 shadow-card ring-1 ring-brand-100/70">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-bold text-ink">{m.name}</p>
                  <p className="text-sm text-ink-soft">{m.email}</p>
                </div>
                <div className="w-40">
                  <Select
                    options={STATUS}
                    value={m.status}
                    onChange={(e) => updateStatus(m.id, e.target.value)}
                  />
                </div>
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm text-ink">{m.message}</p>
              <p className="mt-2 text-xs text-ink-soft">{new Date(m.created_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
