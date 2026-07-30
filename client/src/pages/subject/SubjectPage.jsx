/*
 * Subject page: three section tabs (Lectures, Complete Notes, One Shots).
 *
 * Notes purchasing (all via the shared cart — nothing checks out directly):
 *  - Whole subject / unit → an "Add to cart" toggle in its banner.
 *  - Each chapter → an "Add to cart" button that opens a modal listing the
 *    chapter's notes, where the student can add individual notes and/or the whole
 *    chapter. Fully-owned chapters have no button; adding a higher-level bundle
 *    supersedes the items beneath it so nothing is ever bought twice.
 * Checkout happens from the global cart bar. Prices shown are computed
 * client-side for display; the backend re-prices authoritatively at checkout.
 * After a purchase we refetch the subject so `unlocked` flags flip.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { AppHeader } from "../../components/AppHeader";
import { Footer } from "../../components/Footer";
import { ComingSoon, ComingSoonBadge } from "../../components/ComingSoon";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/Alert";
import { useCart } from "../../cart/CartContext";
import {
  unitDescendantPairs, subjectDescendantPairs, sellableNotes, chapterRowState,
} from "../../cart/cartItems";
import { money, unitPrice, subjectPrice } from "../../lib/pricing";
import { contentApi } from "../../lib/contentApi";
import { ChapterCartModal } from "../../components/ChapterCartModal";
import {
  FiPlayCircle, FiChevronRight, FiFileText, FiLock, FiUnlock, FiCheck, FiShoppingCart,
} from "react-icons/fi";

/* ---- Lectures (units → chapter names; videos live on the chapter page) - */
function ChapterLectureRow({ chapter, subjectSlug }) {
  const count = chapter.lectures.length;
  return (
    <Link
      to={`/subjects/${subjectSlug}/chapters/${chapter.id}`}
      className="flex items-center justify-between gap-4 rounded-2xl bg-surface px-4 py-3 shadow-card ring-1 ring-line transition hover:-translate-y-0.5 hover:shadow-lift"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full bg-brand-100 text-brand-600 dark:text-brand-300">
          <FiPlayCircle className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{chapter.name}</p>
          <p className="text-xs font-semibold text-ink-soft">{count} video{count > 1 ? "s" : ""}</p>
        </div>
      </div>
      <FiChevronRight className="h-5 w-5 flex-shrink-0 text-ink-soft" />
    </Link>
  );
}

function LecturesSection({ units, subjectSlug }) {
  const hasAny = units.some((u) => u.chapters.some((c) => c.lectures.length));
  if (!hasAny) return <ComingSoon title="Lectures coming soon" message="Video lectures will appear here." />;
  return (
    <div className="space-y-8">
      {units.map((unit) => {
        const chapters = unit.chapters.filter((c) => c.lectures.length);
        if (!chapters.length) return null;
        return (
          <div key={unit.id}>
            <div className="mb-3 flex items-center gap-2">
              <h3 className="text-lg font-bold text-ink">{unit.name}</h3>
              {unit.is_coming_soon && <ComingSoonBadge />}
            </div>
            <div className="space-y-2.5">
              {chapters.map((ch) => (
                <ChapterLectureRow key={ch.id} chapter={ch} subjectSlug={subjectSlug} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ---- Notes ------------------------------------------------------------- */
// A plain chapter row that just links to the chapter's notes page — used for
// coming-soon, already-unlocked, bundle-covered, and nothing-to-buy chapters.
function ChapterLinkRow({ to, name, sub, subTone = "text-ink-soft" }) {
  return (
    <Link
      to={to}
      className="flex items-center justify-between gap-4 rounded-2xl bg-surface px-4 py-3 shadow-card ring-1 ring-line transition hover:-translate-y-0.5 hover:shadow-lift"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full bg-brand-100 text-brand-600 dark:text-brand-300">
          <FiFileText className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{name}</p>
          <p className={`text-xs font-semibold ${subTone}`}>{sub}</p>
        </div>
      </div>
      <FiChevronRight className="h-5 w-5 flex-shrink-0 text-ink-soft" />
    </Link>
  );
}

// A chapter row in the Notes tab. Shows an "Add to cart" button that opens the
// chapter modal, unless the chapter is coming soon / already owned / covered by a
// bundle already in the cart / has nothing individually purchasable.
function ChapterNotesRow({ chapter, unit, subject, cart, onAddToCart }) {
  const notesPath = `/subjects/${subject.slug}/chapters/${chapter.id}/notes`;
  const notes = chapter.notes || [];
  const count = notes.length;
  const countLabel = `${count} note${count === 1 ? "" : "s"}`;

  const state = chapterRowState(chapter, {
    unitInCart: cart.has("unit", unit.id),
    subjectInCart: cart.has("subject", subject.id),
  });

  if (state === "coming_soon") {
    return (
      <div className="flex items-center gap-2 rounded-2xl bg-surface px-4 py-3 shadow-card ring-1 ring-line">
        <h4 className="font-bold text-ink">{chapter.name}</h4>
        <ComingSoonBadge />
      </div>
    );
  }
  // Already owned outright → no buy button; link out to read.
  if (state === "owned") {
    return <ChapterLinkRow to={notesPath} name={chapter.name} sub="Unlocked" subTone="text-teal-700 dark:text-teal-300" />;
  }
  // A parent unit/subject bundle is already in the cart → this chapter is covered.
  if (state === "covered") {
    return <ChapterLinkRow to={notesPath} name={chapter.name} sub="Included in your cart bundle" subTone="text-teal-700 dark:text-teal-300" />;
  }
  // Nothing individually purchasable (e.g. only free notes) → simple link.
  if (state === "plain") {
    return <ChapterLinkRow to={notesPath} name={chapter.name} sub={countLabel} />;
  }

  // state === "buyable"
  const sellable = sellableNotes(notes);
  const chapterInCart = cart.has("chapter", chapter.id);
  const notesInCart = sellable.reduce((n, note) => n + (cart.has("note", note.id) ? 1 : 0), 0);
  const anyInCart = chapterInCart || notesInCart > 0;

  const cartNote = chapterInCart
    ? " · whole chapter in cart"
    : notesInCart > 0
      ? ` · ${notesInCart} in cart`
      : "";

  return (
    <div className="flex items-center justify-between gap-3 rounded-2xl bg-surface px-4 py-3 shadow-card ring-1 ring-line transition hover:shadow-lift">
      <Link to={notesPath} className="group flex min-w-0 flex-1 items-center gap-3">
        <span className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full bg-brand-100 text-brand-600 dark:text-brand-300">
          <FiFileText className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink group-hover:text-brand-700 dark:group-hover:text-brand-300">{chapter.name}</p>
          <p className="text-xs font-semibold text-ink-soft">
            {countLabel}
            {cartNote && <span className="text-gold-700 dark:text-gold-300">{cartNote}</span>}
          </p>
        </div>
      </Link>
      <button
        type="button"
        onClick={() => onAddToCart(chapter, unit.id)}
        className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition ${
          anyInCart
            ? "bg-gold-500 text-white hover:bg-gold-600"
            : "border border-gold-300 text-gold-700 dark:text-gold-300 hover:bg-gold-50"
        }`}
      >
        {anyInCart ? <FiCheck className="h-4 w-4" /> : <FiShoppingCart className="h-4 w-4" />}
        <span className="hidden sm:inline">{anyInCart ? "In cart" : "Add to cart"}</span>
      </button>
    </div>
  );
}

export function NotesSection({ subject }) {
  const cart = useCart();
  const [modal, setModal] = useState(null); // { chapter, unitId }

  const hasAny = subject.units.some((u) => u.chapters.length);
  if (!hasAny) return <ComingSoon title="Notes coming soon" message="Complete notes will be available here." />;

  const subjectFullyUnlocked = subject.units.every((u) =>
    u.chapters.every((c) => c.unlocked || c.is_coming_soon)
  );

  const subjectInCart = cart.has("subject", subject.id);
  const addSubject = () => { cart.removeMany(subjectDescendantPairs(subject)); cart.add("subject", subject.id); };

  return (
    <div className="space-y-8 pb-28">
      {!subjectFullyUnlocked && subject.bundle_purchasable && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-card bg-navy-800 px-6 py-5 text-white shadow-soft">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-gold-500/20 text-gold-300">
              <FiUnlock className="h-5 w-5" />
            </span>
            <div>
              <p className="font-bold">Unlock all {subject.name} notes</p>
              <p className="text-sm text-navy-200">One bundle unlocks every chapter — including ones added later.</p>
            </div>
          </div>
          <Button
            variant="premium"
            icon={subjectInCart ? FiCheck : FiShoppingCart}
            onClick={subjectInCart ? () => cart.remove("subject", subject.id) : addSubject}
          >
            {subjectInCart ? "Added to cart" : `Add to cart · ${money(subjectPrice(subject))}`}
          </Button>
        </div>
      )}

      {subject.units.map((unit) => {
        const unitUnlocked = unit.chapters.every((c) => c.unlocked || c.is_coming_soon);
        const unitCoveredBySubject = cart.has("subject", subject.id);
        const unitInCart = cart.has("unit", unit.id);
        const addUnit = () => { cart.removeMany(unitDescendantPairs(unit)); cart.add("unit", unit.id); };
        const showUnitBuy = !unitUnlocked && !unit.is_coming_soon && unit.bundle_purchasable && !unitCoveredBySubject;
        return (
          <div key={unit.id}>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-bold text-ink">{unit.name}</h3>
              {unit.is_coming_soon && <ComingSoonBadge />}
            </div>

            {showUnitBuy && (
              <div className="mb-3 flex w-full flex-wrap items-center justify-between gap-3 rounded-card border border-gold-200 bg-gold-50 px-4 py-3 text-left">
                <span className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gold-500/15 text-gold-700 dark:text-gold-300">
                    <FiLock className="h-4 w-4" />
                  </span>
                  <span>
                    <span className="block text-sm font-bold text-gold-700 dark:text-gold-300">Complete unit</span>
                    <span className="block text-xs text-gold-700/80 dark:text-gold-300/90">Unlocks every chapter &amp; note in this unit — including any added later.</span>
                  </span>
                </span>
                <button
                  onClick={unitInCart ? () => cart.remove("unit", unit.id) : addUnit}
                  aria-pressed={unitInCart}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-semibold transition ${
                    unitInCart ? "bg-gold-500 text-white hover:bg-gold-600" : "border border-gold-400 text-gold-700 dark:text-gold-300 hover:bg-gold-100/60"
                  }`}
                >
                  {unitInCart ? <><FiCheck className="h-3.5 w-3.5" /> Added</> : <>Add · {money(unitPrice(unit))}</>}
                </button>
              </div>
            )}

            {unitCoveredBySubject && !unitUnlocked && !unit.is_coming_soon && (
              <div className="mb-3 rounded-card bg-teal-50 px-4 py-2 text-xs font-medium text-teal-700 ring-1 ring-teal-100 dark:text-teal-300">
                This unit is included in the subject bundle in your cart.
              </div>
            )}

            <div className="space-y-2.5">
              {unit.chapters.map((ch) => (
                <ChapterNotesRow
                  key={ch.id}
                  chapter={ch}
                  unit={unit}
                  subject={subject}
                  cart={cart}
                  onAddToCart={(chapter, unitId) => setModal({ chapter, unitId })}
                />
              ))}
            </div>
          </div>
        );
      })}

      <ChapterCartModal
        chapter={modal?.chapter || null}
        subjectId={subject.id}
        unitId={modal?.unitId}
        onClose={() => setModal(null)}
      />
    </div>
  );
}

/* ---- Page -------------------------------------------------------------- */
export default function SubjectPage() {
  const { slug } = useParams();
  const { purchaseVersion } = useCart();
  const [subject, setSubject] = useState(null);
  const [error, setError] = useState(null);
  const [activeKind, setActiveKind] = useState(null);

  // Remember which tab was open per subject, so returning from a lecture/notes
  // page (browser back) lands on the same tab instead of resetting to the first.
  const tabKey = `digikart_subject_tab_${slug}`;

  const load = useCallback(() => {
    return contentApi.subject(slug).then((data) => {
      setSubject(data);
      setActiveKind((k) => {
        if (k) return k;
        const saved = sessionStorage.getItem(tabKey);
        const restored = data.sections.some((s) => s.kind === saved) ? saved : null;
        return restored || data.sections[0]?.kind || null;
      });
      document.title = `${data.name} · Digikart`;
    });
  }, [slug, tabKey]);

  useEffect(() => {
    setSubject(null);
    setError(null);
    load().catch(() => setError("Could not load this subject."));
  }, [load]);

  // Refresh unlock flags after any purchase (via the global cart bar) without
  // blanking the page. Skips the initial mount.
  const pvRef = useRef(purchaseVersion);
  useEffect(() => {
    if (pvRef.current === purchaseVersion) return;
    pvRef.current = purchaseVersion;
    load().catch(() => {});
  }, [purchaseVersion, load]);

  // Persist the active tab whenever it changes.
  useEffect(() => {
    if (activeKind) sessionStorage.setItem(tabKey, activeKind);
  }, [activeKind, tabKey]);

  const activeSection = useMemo(
    () => subject?.sections.find((s) => s.kind === activeKind) || null,
    [subject, activeKind]
  );

  if (error) return <Shell><Alert tone="error" action={{ label: "Retry", onClick: () => window.location.reload() }}>{error}</Alert></Shell>;
  if (!subject) return <Shell><div className="flex justify-center py-20 text-brand-600 dark:text-brand-300"><Spinner className="h-9 w-9" /></div></Shell>;

  return (
    <Shell>
      <nav className="mb-3 flex flex-wrap items-center gap-1 text-sm text-ink-soft">
        <Link to="/dashboard" className="font-medium text-brand-700 dark:text-brand-300 hover:underline">Dashboard</Link>
        <span className="text-brand-300">/</span>
        <span>{subject.year.title}</span>
        <span className="text-brand-300">/</span>
        <span className="font-medium text-ink">{subject.name}</span>
      </nav>

      <div className="flex items-center gap-3">
        <h1 className="text-3xl font-extrabold tracking-tight text-ink">{subject.name}</h1>
        {subject.is_coming_soon && <ComingSoonBadge />}
      </div>
      {subject.description && <p className="mt-2 max-w-2xl text-ink-soft">{subject.description}</p>}

      {subject.is_coming_soon ? (
        <div className="mt-8"><ComingSoon /></div>
      ) : (
        <>
          <div className="mt-7 flex flex-wrap gap-2 border-b border-brand-100">
            {subject.sections.map((s) => (
              <button
                key={s.kind}
                onClick={() => setActiveKind(s.kind)}
                className={[
                  "flex items-center gap-2 rounded-t-xl px-4 py-2.5 text-sm font-semibold transition",
                  activeKind === s.kind ? "bg-surface text-brand-700 dark:text-brand-300 shadow-card ring-1 ring-brand-100" : "text-ink-soft hover:text-brand-700 dark:hover:text-brand-300",
                ].join(" ")}
              >
                {s.label}
                {s.is_coming_soon && <ComingSoonBadge />}
              </button>
            ))}
          </div>

          <div className="mt-6">
            {!activeSection ? (
              <ComingSoon title="Nothing here yet" />
            ) : activeSection.is_coming_soon ? (
              <ComingSoon title={`${activeSection.label} — Coming Soon`} />
            ) : activeSection.kind === "lectures" ? (
              <LecturesSection units={subject.units} subjectSlug={subject.slug} />
            ) : activeSection.kind === "notes" ? (
              <NotesSection subject={subject} />
            ) : (
              <ComingSoon title="One Shots — Coming Soon" message="Quick revision one-shots are on the way." />
            )}
          </div>
        </>
      )}
    </Shell>
  );
}

function Shell({ children }) {
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
      <Footer />
    </div>
  );
}
