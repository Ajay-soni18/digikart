/*
 * Protected notes viewer. Opens a single note (chosen via ?note=<id>, falling
 * back to the chapter's first note) and:
 *  - note unlocked → renders the watermarked PdfViewer
 *  - note locked   → an add-to-cart panel: add this note, and/or the whole
 *                    chapter when the admin sells it as a bundle. Adding the
 *                    chapter supersedes its individual notes in the cart.
 * Checkout happens from the global cart bar. Browsing/buying across the chapter's
 * notes also lives on the chapter notes page (ChapterNotes); access is ultimately
 * enforced by the backend on the file request itself.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { AppHeader } from "../../components/AppHeader";
import { PdfViewer } from "../../components/pdf/PdfViewer";
import { ProtectedContent } from "../../components/ProtectedContent";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/Alert";
import { FiLock, FiUnlock, FiCheck, FiShoppingCart } from "react-icons/fi";
import { useCart } from "../../cart/CartContext";
import { notePairs } from "../../cart/cartItems";
import { money } from "../../lib/pricing";
import { api } from "../../lib/api";

// Add-to-cart panel shown when the active note is locked.
export function NoteLocked({ note, chapter, noteInCart, chapterInCart, onToggleNote, onToggleChapter }) {
  const sellable = !note.is_free && Number(note.price) > 0;
  const covered = chapterInCart; // the whole chapter in the cart already covers this note
  return (
    <div className="p-10 text-center">
      <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-gold-100 text-gold-600 dark:text-gold-300">
        <FiLock className="h-6 w-6" />
      </span>
      <h2 className="mt-4 text-xl font-bold text-ink">{note.title}</h2>
      <p className="mt-1 text-ink-soft">This note is locked. Add it to your cart to unlock the complete, protected notes.</p>
      <div className="mt-6 flex flex-col items-center gap-3">
        {sellable && !covered && (
          <Button variant="premium" size="lg" icon={noteInCart ? FiCheck : FiShoppingCart} onClick={onToggleNote}>
            {noteInCart ? "Added to cart" : `Add note to cart · ${money(note.price)}`}
          </Button>
        )}
        {sellable && covered && (
          <p className="text-sm font-medium text-gold-700 dark:text-gold-300">Included with the chapter in your cart</p>
        )}
        {chapter.bundle_purchasable && (
          <Button
            variant={sellable && !covered ? "outline" : "premium"}
            size="lg"
            icon={chapterInCart ? FiCheck : FiUnlock}
            onClick={onToggleChapter}
          >
            {chapterInCart ? "Chapter added to cart" : `Add chapter to cart · ${money(chapter.bundle_price)}`}
          </Button>
        )}
        {!sellable && !chapter.bundle_purchasable && (
          <p className="text-sm text-ink-soft">This note isn’t available for purchase yet.</p>
        )}
        <span className="text-xs text-ink-soft">Add to cart, then check out from the cart bar below.</span>
      </div>
    </div>
  );
}

export default function NotesViewer() {
  const { slug, chapterId } = useParams();
  const { has, add, remove, toggle, removeMany, purchaseVersion } = useCart();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [activeNoteId, setActiveNoteId] = useState(null);

  const fetchContext = () =>
    api
      .get(`/chapters/${chapterId}/notes/`)
      .then((r) => {
        // Keep the current note if it still exists; else open ?note=<id>, else the first.
        const raw = searchParams.get("note");
        const wanted = Number(raw);
        const wantedExists = r.data.notes.some((n) => n.id === wanted);
        // A ?note= that doesn't resolve to a real note in this chapter is invalid
        // (bad id, non-numeric, deleted note) — send the student to the chapter's
        // notes listing rather than silently opening some other note.
        if (raw !== null && !wantedExists && !activeNoteId) {
          navigate(`/subjects/${slug}/chapters/${chapterId}/notes`, { replace: true });
          return;
        }
        setData(r.data);
        setActiveNoteId((cur) =>
          cur && r.data.notes.some((n) => n.id === cur)
            ? cur
            : wantedExists ? wanted : r.data.notes[0]?.id ?? null
        );
        document.title = `${r.data.chapter.name} · Notes`;
      })
      .catch((e) => setError(e?.response?.status === 404 ? "Chapter not found." : "Could not load notes."));

  useEffect(() => {
    setData(null);
    setError(null);
    fetchContext();
  }, [chapterId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Refresh after any purchase (via the global cart bar) so a just-bought note
  // flips from the locked panel to the reader. Skips the initial mount and does
  // not blank the page.
  const pvRef = useRef(purchaseVersion);
  useEffect(() => {
    if (pvRef.current === purchaseVersion) return;
    pvRef.current = purchaseVersion;
    fetchContext();
  }, [purchaseVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeNote = useMemo(
    () => data?.notes.find((n) => n.id === activeNoteId) || null,
    [data, activeNoteId]
  );

  // Adding the whole chapter supersedes its individual notes already in the cart.
  const toggleChapter = () => {
    const chId = data.chapter.id;
    if (has("chapter", chId)) {
      remove("chapter", chId);
    } else {
      removeMany(notePairs(data.notes));
      add("chapter", chId);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <AppHeader />
      <main className="mx-auto max-w-5xl px-4 pb-28 pt-6 sm:px-6">
        <nav className="mb-4 flex items-center gap-1 text-sm">
          <Link to={`/subjects/${slug}/chapters/${chapterId}/notes`} className="font-medium text-brand-700 dark:text-brand-300 hover:underline">
            ← Back to notes
          </Link>
        </nav>

        <Alert tone="error" action={error ? { label: "Retry", onClick: () => { setError(null); fetchContext(); } } : undefined}>
          {error}
        </Alert>

        {!data && !error && (
          <div className="flex justify-center py-20 text-brand-600 dark:text-brand-300"><Spinner className="h-9 w-9" /></div>
        )}

        {data && (
          <>
            <div className="mb-4">
              <h1 className="text-2xl font-extrabold tracking-tight text-ink">{data.chapter.name}</h1>
              <p className="text-sm text-ink-soft">{data.chapter.subject}</p>
            </div>

            {data.notes.length === 0 ? (
              <div className="rounded-card border border-dashed border-brand-200 bg-surface/60 p-10 text-center text-ink-soft">
                Notes for this chapter are coming soon.
              </div>
            ) : (
              <div className="rounded-card bg-surface shadow-card ring-1 ring-brand-100">
                {activeNote && activeNote.unlocked ? (
                  <ProtectedContent>
                    <PdfViewer noteId={activeNote.id} version={activeNote.version} />
                  </ProtectedContent>
                ) : activeNote ? (
                  <NoteLocked
                    note={activeNote}
                    chapter={data.chapter}
                    noteInCart={has("note", activeNote.id)}
                    chapterInCart={has("chapter", data.chapter.id)}
                    onToggleNote={() => toggle("note", activeNote.id)}
                    onToggleChapter={toggleChapter}
                  />
                ) : null}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
