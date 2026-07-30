/*
 * Chapter notes listing page.
 *
 * Reached by clicking a chapter name in a subject's Notes tab. Lists every note
 * in the chapter and lets the student add to the shared cart:
 *   - a single note (tap "Add"), or
 *   - the whole chapter as a bundle (when the admin sells it) — which supersedes
 *     its individual notes already in the cart.
 * Checkout happens from the global cart bar. Unlocked notes open in the protected
 * PDF viewer. Prices are shown for display; the backend re-prices authoritatively
 * at checkout. After a successful purchase we refetch so `unlocked` flags flip.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { AppHeader } from "../../components/AppHeader";
import { Footer } from "../../components/Footer";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/Alert";
import { useCart } from "../../cart/CartContext";
import { notePairs } from "../../cart/cartItems";
import { money } from "../../lib/pricing";
import { api } from "../../lib/api";
import { FiLock, FiUnlock, FiFileText, FiCheck, FiShoppingCart } from "react-icons/fi";

function IconChip({ tone, children }) {
  return <span className={`grid h-9 w-9 flex-shrink-0 place-items-center rounded-full ${tone}`}>{children}</span>;
}

function Row({ lead, name, sub, subTone = "text-ink-soft", right }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl bg-surface px-4 py-3 shadow-card ring-1 ring-line transition hover:shadow-lift">
      <div className="flex min-w-0 items-center gap-3">
        {lead}
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{name}</p>
          {sub && <p className={`text-xs font-semibold ${subTone}`}>{sub}</p>}
        </div>
      </div>
      <div className="flex-shrink-0">{right}</div>
    </div>
  );
}

// Gold add/remove pill for the note cart toggle.
function AddPill({ checked, onClick }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={checked}
      className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-semibold transition ${
        checked ? "bg-gold-500 text-white hover:bg-gold-600" : "border border-gold-300 text-gold-700 dark:text-gold-300 hover:bg-gold-50"
      }`}
    >
      {checked && <FiCheck className="h-4 w-4" />}
      {checked ? "Added" : "Add"}
    </button>
  );
}

// One note: Read when unlocked; a priced cart toggle when sold on its own;
// "Included with chapter" when it's a free-in-bundle note or the whole chapter is
// already in the cart; otherwise only reachable by buying the chapter/a parent.
function NoteRow({ note, onRead, chapterInCart, inCart, onToggle }) {
  if (note.unlocked) {
    return (
      <Row
        lead={<IconChip tone="bg-teal-100 text-teal-600 dark:text-teal-300"><FiUnlock className="h-4 w-4" /></IconChip>}
        name={note.title}
        sub={note.is_free ? "Free" : "Unlocked"}
        subTone="text-teal-700 dark:text-teal-300"
        right={<Button size="sm" variant="success" icon={FiFileText} onClick={onRead}>Read</Button>}
      />
    );
  }
  const lock = <IconChip tone="bg-gold-100 text-gold-600 dark:text-gold-300"><FiLock className="h-4 w-4" /></IconChip>;
  const sellable = !note.is_free && Number(note.price) > 0;
  if (!sellable || chapterInCart) {
    // Free-in-bundle, or superseded by the whole chapter sitting in the cart.
    return (
      <Row lead={lock} name={note.title}
        sub={sellable ? money(note.price) : undefined}
        subTone="text-gold-700 dark:text-gold-300"
        right={<span className="text-xs font-medium text-ink-soft">Included with chapter</span>} />
    );
  }
  return (
    <Row
      lead={lock}
      name={note.title}
      sub={money(note.price)}
      subTone="text-gold-700 dark:text-gold-300"
      right={<AddPill checked={inCart} onClick={onToggle} />}
    />
  );
}

/* ---- Page -------------------------------------------------------------- */
export default function ChapterNotes() {
  const { slug, chapterId } = useParams();
  const navigate = useNavigate();
  const { has, add, remove, removeMany, toggle, purchaseVersion } = useCart();

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fetchContext = useCallback(() => {
    return api
      .get(`/chapters/${chapterId}/notes/`)
      .then((r) => {
        setData(r.data);
        document.title = `${r.data.chapter.name} · Notes`;
      })
      .catch((e) => setError(e?.response?.status === 404 ? "Chapter not found." : "Could not load notes."));
  }, [chapterId]);

  useEffect(() => {
    setData(null);
    setError(null);
    fetchContext();
  }, [fetchContext]);

  // Refresh unlock flags after any purchase (via the global cart bar) without
  // blanking the page to a spinner. Skips the initial mount.
  const pvRef = useRef(purchaseVersion);
  useEffect(() => {
    if (pvRef.current === purchaseVersion) return;
    pvRef.current = purchaseVersion;
    fetchContext();
  }, [purchaseVersion, fetchContext]);

  const chapter = data?.chapter;
  const chapterInCart = chapter ? has("chapter", chapter.id) : false;
  const showChapterCta = chapter && !chapter.unlocked && chapter.bundle_purchasable;

  // Adding the whole chapter supersedes its individual notes already in the cart.
  const addChapter = () => {
    removeMany(notePairs(data.notes));
    add("chapter", chapter.id);
  };

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6">
        <nav className="mb-4 flex items-center gap-1 text-sm">
          <Link to={`/subjects/${slug}`} className="font-medium text-brand-700 dark:text-brand-300 hover:underline">
            ← Back to subject
          </Link>
        </nav>

        {error && (
          <Alert tone="error" action={{ label: "Retry", onClick: () => { setError(null); fetchContext(); } }}>
            {error}
          </Alert>
        )}

        {!data && !error && (
          <div className="flex justify-center py-20 text-brand-600 dark:text-brand-300"><Spinner className="h-9 w-9" /></div>
        )}

        {data && (
          <>
            <div className="mb-5">
              <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">{chapter.name}</h1>
              <p className="text-sm text-ink-soft">{chapter.subject}</p>
            </div>

            {showChapterCta && (
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-card border border-gold-200 bg-gold-50 px-4 py-3">
                <span className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gold-500/15 text-gold-700 dark:text-gold-300">
                    <FiUnlock className="h-4 w-4" />
                  </span>
                  <span>
                    <span className="block text-sm font-bold text-gold-700 dark:text-gold-300">Complete chapter</span>
                    <span className="block text-xs text-gold-700/80 dark:text-gold-300/90">Unlocks every note in this chapter — including any added later.</span>
                  </span>
                </span>
                <button
                  onClick={chapterInCart ? () => remove("chapter", chapter.id) : addChapter}
                  aria-pressed={chapterInCart}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-semibold transition ${
                    chapterInCart ? "bg-gold-500 text-white hover:bg-gold-600" : "border border-gold-400 text-gold-700 dark:text-gold-300 hover:bg-gold-100/60"
                  }`}
                >
                  {chapterInCart ? <><FiCheck className="h-4 w-4" /> Added to cart</> : <><FiShoppingCart className="h-4 w-4" /> Add · {money(chapter.bundle_price)}</>}
                </button>
              </div>
            )}

            {data.notes.length === 0 ? (
              <div className="rounded-card border border-dashed border-brand-200 bg-surface/60 p-10 text-center text-ink-soft">
                Notes for this chapter are coming soon.
              </div>
            ) : (
              <div className="space-y-2 pb-28">
                {data.notes.map((n) => (
                  <NoteRow
                    key={n.id}
                    note={n}
                    onRead={() => navigate(`/subjects/${slug}/notes/${chapterId}?note=${n.id}`)}
                    chapterInCart={chapterInCart}
                    inCart={has("note", n.id)}
                    onToggle={() => toggle("note", n.id)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>

      <Footer />
    </div>
  );
}
