/* Public Help & Contact page — posts a doubt/support request to the admin inbox. */
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { FiCheckCircle } from "react-icons/fi";
import { Logo } from "../components/Logo";
import { Footer } from "../components/Footer";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Textarea } from "../components/ui/fields";
import { Alert } from "../components/ui/Alert";
import { useAuth } from "../auth/AuthContext";
import { api, apiError } from "../lib/api";
import { engagementApi } from "../lib/engagementApi";

export default function Contact() {
  const { user } = useAuth();
  const [form, setForm] = useState({ name: "", email: "", message: "" });
  const [helpText, setHelpText] = useState("");
  const [state, setState] = useState({ sending: false, sent: false, error: null });

  useEffect(() => {
    document.title = "Help & Contact · Digikart";
    api.get("/site-content/").then((r) => setHelpText(r.data.help_text || "")).catch(() => {});
  }, []);

  useEffect(() => {
    if (user) setForm((f) => ({ ...f, name: user.full_name || "", email: user.email || "" }));
  }, [user]);

  const onChange = (e) => setForm((f) => ({ ...f, [e.target.name]: e.target.value }));

  const onSubmit = async (e) => {
    e.preventDefault();
    setState({ sending: true, sent: false, error: null });
    try {
      await engagementApi.contact(form);
      setState({ sending: false, sent: true, error: null });
      setForm((f) => ({ ...f, message: "" }));
    } catch (err) {
      setState({ sending: false, sent: false, error: apiError(err, "Could not send your message.") });
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <Logo imgClassName="h-11 w-auto" />
        <Link to="/" className="text-sm font-medium text-brand-700 dark:text-brand-300 hover:underline">← Home</Link>
      </header>

      <main className="mx-auto w-full max-w-xl flex-1 px-6 py-6">
        <h1 className="text-3xl font-extrabold tracking-tight text-ink">Help &amp; Contact</h1>
        {helpText && <p className="mt-2 text-ink-soft">{helpText}</p>}

        <div className="mt-6 rounded-card bg-surface p-6 shadow-card ring-1 ring-brand-100">
          {state.sent ? (
            <div className="rounded-2xl bg-teal-50 px-4 py-8 text-center">
              <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-teal-100 text-teal-600 dark:text-teal-300">
                <FiCheckCircle className="h-6 w-6" />
              </span>
              <p className="mt-3 text-lg font-bold text-teal-800 dark:text-teal-300">Thanks!</p>
              <p className="mt-1 text-sm text-teal-700 dark:text-teal-300">We've received your message and will get back to you soon.</p>
              <Button className="mt-4" variant="outline" onClick={() => setState((s) => ({ ...s, sent: false }))}>
                Send another
              </Button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <Alert tone="error">{state.error}</Alert>
              <Input label="Name" name="name" required value={form.name} onChange={onChange} />
              <Input label="Email" name="email" type="email" required value={form.email} onChange={onChange} />
              <Textarea label="Your message" name="message" required rows={5} value={form.message} onChange={onChange} />
              <Button type="submit" size="lg" loading={state.sending} className="w-full">Send message</Button>
            </form>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
}
