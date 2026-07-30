/*
 * Add-to-cart modal for a single chapter, opened from the subject page.
 *
 * Lists every note in the chapter plus — when the admin sells the chapter as a
 * bundle — an "add the whole chapter" option. Adding the whole chapter supersedes
 * its individual notes in the cart, and while it's selected (or a parent unit /
 * subject is already in the cart) the notes show as "included" — so a chapter and
 * its own notes are never both bought. Owned / free notes are listed for context
 * but have no add button. Everything is priced and authorised server-side at
 * checkout; this only edits the shared cart.
 */
import { FiCheck, FiLock, FiUnlock, FiShoppingCart } from "react-icons/fi";
import { Modal } from "./ui/Modal";
import { Button } from "./ui/Button";
import { useCart } from "../cart/CartContext";
import { notePairs, sellableNotes } from "../cart/cartItems";
import { money } from "../lib/pricing";

function Line({ toneIcon, icon, title, sub, right }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-canvas-2 px-3 py-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className={`grid h-7 w-7 flex-shrink-0 place-items-center rounded-full ${toneIcon}`}>{icon}</span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{title}</p>
          {sub && <p className="text-xs font-semibold text-gold-700 dark:text-gold-300">{sub}</p>}
        </div>
      </div>
      <div className="flex-shrink-0">{right}</div>
    </div>
  );
}

function NoteLine({ note, covered, checked, onToggle }) {
  // Already owned (directly or via a bundle) or free — nothing to buy.
  if (note.unlocked) {
    return (
      <Line
        toneIcon="bg-teal-100 text-teal-600 dark:text-teal-300"
        icon={<FiUnlock className="h-3.5 w-3.5" />}
        title={note.title}
        right={<span className="text-xs font-semibold text-teal-700 dark:text-teal-300">{note.is_free ? "Free" : "Owned"}</span>}
      />
    );
  }
  const sellable = !note.is_free && Number(note.price) > 0;
  // A ₹0 non-free note is only obtainable by buying the whole chapter/parent.
  if (!sellable || covered) {
    return (
      <Line
        toneIcon="bg-gold-100 text-gold-600 dark:text-gold-300"
        icon={<FiLock className="h-3.5 w-3.5" />}
        title={note.title}
        sub={sellable ? money(note.price) : null}
        right={<span className="text-xs font-medium text-ink-soft">Included with chapter</span>}
      />
    );
  }
  return (
    <Line
      toneIcon="bg-gold-100 text-gold-600 dark:text-gold-300"
      icon={<FiLock className="h-3.5 w-3.5" />}
      title={note.title}
      sub={money(note.price)}
      right={
        <button
          onClick={onToggle}
          aria-pressed={checked}
          className={`inline-flex flex-shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
            checked ? "bg-gold-500 text-white hover:bg-gold-600" : "border border-gold-300 text-gold-700 dark:text-gold-300 hover:bg-gold-50"
          }`}
        >
          {checked && <FiCheck className="h-3.5 w-3.5" />}
          {checked ? "Added" : "Add"}
        </button>
      }
    />
  );
}

export function ChapterCartModal({ chapter, subjectId, unitId, onClose }) {
  const { has, add, remove, toggle, removeMany, count } = useCart();

  const notes = chapter?.notes || [];
  const chapterInCart = chapter ? has("chapter", chapter.id) : false;
  const coveredByParent = chapter ? (has("unit", unitId) || has("subject", subjectId)) : false;
  const wholeChapterSelected = chapterInCart || coveredByParent;
  const canAddChapter = chapter ? (chapter.bundle_purchasable && !chapter.unlocked && !coveredByParent) : false;

  const sellable = sellableNotes(notes);
  const allNotesAdded = sellable.length > 0 && sellable.every((n) => has("note", n.id));

  // Adding the whole chapter supersedes any of its individual notes in the cart.
  const addChapter = () => {
    removeMany(notePairs(notes));
    add("chapter", chapter.id);
  };
  const toggleAllNotes = () => {
    if (allNotesAdded) removeMany(sellable.map((n) => ({ type: "note", id: n.id })));
    else sellable.forEach((n) => { if (!has("note", n.id)) add("note", n.id); });
  };

  return (
    <Modal open={!!chapter} onClose={onClose} title="Add to cart">
      {chapter && (
        <div className="space-y-4">
          <div>
            <h3 className="text-lg font-bold text-ink">{chapter.name}</h3>
            <p className="text-sm text-ink-soft">{notes.length} note{notes.length === 1 ? "" : "s"} in this chapter</p>
          </div>

          {coveredByParent && (
            <div className="rounded-2xl bg-teal-50 px-4 py-3 text-sm font-medium text-teal-700 ring-1 ring-teal-100 dark:text-teal-300">
              This chapter is already included in a bundle in your cart.
            </div>
          )}

          {canAddChapter && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gold-200 bg-gold-50 px-4 py-3">
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
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-semibold transition ${
                  chapterInCart ? "bg-gold-500 text-white hover:bg-gold-600" : "border border-gold-400 text-gold-700 dark:text-gold-300 hover:bg-gold-100/60"
                }`}
              >
                {chapterInCart ? <><FiCheck className="h-4 w-4" /> Added</> : <>Add · {money(chapter.bundle_price)}</>}
              </button>
            </div>
          )}

          {notes.length > 0 && (
            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
                  {canAddChapter ? "Or add individual notes" : "Notes"}
                </p>
                {!wholeChapterSelected && sellable.length > 1 && (
                  <button
                    onClick={toggleAllNotes}
                    className="shrink-0 rounded-full border border-gold-300 px-3 py-1 text-xs font-semibold text-gold-700 dark:text-gold-300 transition-colors hover:bg-gold-50"
                  >
                    {allNotesAdded ? "Remove all" : `Add all ${sellable.length}`}
                  </button>
                )}
              </div>
              <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-1">
                {notes.map((n) => (
                  <NoteLine
                    key={n.id}
                    note={n}
                    covered={wholeChapterSelected}
                    checked={has("note", n.id)}
                    onToggle={() => toggle("note", n.id)}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
            <span className="flex items-center gap-1.5 text-xs font-medium text-ink-soft">
              <FiShoppingCart className="h-3.5 w-3.5" />
              {count > 0 ? `${count} item${count === 1 ? "" : "s"} in your cart` : "Your cart is empty"}
            </span>
            <Button variant="secondary" onClick={onClose}>Done</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
