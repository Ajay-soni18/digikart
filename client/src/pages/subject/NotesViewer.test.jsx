import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// NoteLocked is a pure panel; stub the heavy pdf.js viewer so importing the
// module doesn't pull in pdfjs-dist.
vi.mock("../../components/pdf/PdfViewer", () => ({ PdfViewer: () => null }));

import { NoteLocked } from "./NotesViewer";

const sellableNote = () => ({ title: "N", price: "40.00", is_free: false, unlocked: false });
const bundleChapter = () => ({ bundle_purchasable: true, bundle_price: "100.00" });

function renderPanel(props = {}) {
  const onToggleNote = vi.fn();
  const onToggleChapter = vi.fn();
  render(
    <NoteLocked
      note={props.note ?? sellableNote()}
      chapter={props.chapter ?? bundleChapter()}
      noteInCart={props.noteInCart ?? false}
      chapterInCart={props.chapterInCart ?? false}
      onToggleNote={onToggleNote}
      onToggleChapter={onToggleChapter}
    />
  );
  return { onToggleNote, onToggleChapter };
}

describe("NoteLocked purchase panel", () => {
  it("offers both note and chapter add-to-cart, and fires the callbacks", () => {
    const { onToggleNote, onToggleChapter } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /Add note to cart · ₹40/ }));
    expect(onToggleNote).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /Add chapter to cart · ₹100/ }));
    expect(onToggleChapter).toHaveBeenCalledTimes(1);
  });

  it("reflects the in-cart state on the buttons", () => {
    renderPanel({ noteInCart: true });
    expect(screen.getByRole("button", { name: /Added to cart/ })).toBeInTheDocument();
  });

  it("hides the note button and shows 'included' once the whole chapter is in the cart", () => {
    renderPanel({ chapterInCart: true });
    expect(screen.getByText(/included with the chapter in your cart/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add note to cart/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Chapter added to cart/ })).toBeInTheDocument();
  });

  it("shows a 'not available' message when nothing is purchasable", () => {
    renderPanel({
      note: { title: "N", price: "0.00", is_free: false, unlocked: false }, // bundle-only, ₹0
      chapter: { bundle_purchasable: false, bundle_price: null },
    });
    expect(screen.getByText(/isn.t available for purchase yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
