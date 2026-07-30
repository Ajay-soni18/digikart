import { describe, it, expect } from "vitest";
import {
  cartKey,
  notePairs,
  chapterNotePairs,
  unitDescendantPairs,
  subjectDescendantPairs,
  isNoteSellable,
  sellableNotes,
  chapterRowState,
} from "./cartItems";

describe("cartKey", () => {
  it("namespaces the id by type so a note and a chapter with the same id never collide", () => {
    expect(cartKey("note", 5)).toBe("note:5");
    expect(cartKey("chapter", 5)).toBe("chapter:5");
    expect(cartKey("note", 5)).not.toBe(cartKey("chapter", 5));
  });
});

describe("notePairs / chapterNotePairs", () => {
  it("maps notes to { type: 'note', id }", () => {
    expect(notePairs([{ id: 1 }, { id: 2 }])).toEqual([
      { type: "note", id: 1 },
      { type: "note", id: 2 },
    ]);
  });
  it("tolerates missing/empty input", () => {
    expect(notePairs()).toEqual([]);
    expect(notePairs([])).toEqual([]);
    expect(chapterNotePairs({})).toEqual([]);
    expect(chapterNotePairs(null)).toEqual([]);
    expect(chapterNotePairs({ notes: [{ id: 9 }] })).toEqual([{ type: "note", id: 9 }]);
  });
});

describe("unitDescendantPairs", () => {
  it("lists every chapter and its notes beneath a unit", () => {
    const unit = {
      chapters: [
        { id: 10, notes: [{ id: 100 }, { id: 101 }] },
        { id: 11, notes: [] },
      ],
    };
    expect(unitDescendantPairs(unit)).toEqual([
      { type: "chapter", id: 10 },
      { type: "note", id: 100 },
      { type: "note", id: 101 },
      { type: "chapter", id: 11 },
    ]);
  });
});

describe("subjectDescendantPairs", () => {
  it("lists every unit, chapter and note beneath a subject", () => {
    const subject = {
      units: [
        { id: 1, chapters: [{ id: 10, notes: [{ id: 100 }] }] },
        { id: 2, chapters: [] },
      ],
    };
    expect(subjectDescendantPairs(subject)).toEqual([
      { type: "unit", id: 1 },
      { type: "chapter", id: 10 },
      { type: "note", id: 100 },
      { type: "unit", id: 2 },
    ]);
  });
});

describe("isNoteSellable", () => {
  it("is true only for a locked, priced, non-free note", () => {
    expect(isNoteSellable({ price: "40", is_free: false, unlocked: false })).toBe(true);
  });
  it("is false for free, owned, or ₹0 notes", () => {
    expect(isNoteSellable({ price: "40", is_free: true, unlocked: false })).toBe(false); // free
    expect(isNoteSellable({ price: "40", is_free: false, unlocked: true })).toBe(false); // owned
    expect(isNoteSellable({ price: "0", is_free: false, unlocked: false })).toBe(false); // ₹0 (bundle-only)
  });
});

describe("sellableNotes", () => {
  it("keeps only the individually-sellable notes", () => {
    const notes = [
      { id: 1, price: "40", is_free: false, unlocked: false }, // sellable
      { id: 2, price: "0", is_free: true, unlocked: true }, // free
      { id: 3, price: "50", is_free: false, unlocked: true }, // owned
      { id: 4, price: "0", is_free: false, unlocked: false }, // bundle-only
    ];
    expect(sellableNotes(notes).map((n) => n.id)).toEqual([1]);
    expect(sellableNotes()).toEqual([]);
  });
});

describe("chapterRowState", () => {
  const buyable = { bundle_purchasable: true, notes: [] };

  it("returns coming_soon first, regardless of other flags", () => {
    expect(chapterRowState({ is_coming_soon: true, unlocked: true, bundle_purchasable: true })).toBe("coming_soon");
  });
  it("returns owned when unlocked (before covered)", () => {
    expect(chapterRowState({ unlocked: true }, { subjectInCart: true })).toBe("owned");
  });
  it("returns covered when a parent unit or subject is in the cart", () => {
    expect(chapterRowState(buyable, { unitInCart: true })).toBe("covered");
    expect(chapterRowState(buyable, { subjectInCart: true })).toBe("covered");
  });
  it("returns buyable for a purchasable bundle", () => {
    expect(chapterRowState({ bundle_purchasable: true, notes: [] })).toBe("buyable");
  });
  it("returns buyable when it has at least one sellable note (even if no bundle)", () => {
    expect(
      chapterRowState({ bundle_purchasable: false, notes: [{ price: "40", is_free: false, unlocked: false }] })
    ).toBe("buyable");
  });
  it("returns plain when nothing is individually purchasable", () => {
    expect(
      chapterRowState({ bundle_purchasable: false, notes: [{ price: "0", is_free: true, unlocked: true }] })
    ).toBe("plain");
    expect(chapterRowState({ bundle_purchasable: false, notes: [] })).toBe("plain");
  });
});
