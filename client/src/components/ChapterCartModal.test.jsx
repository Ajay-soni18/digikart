import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CartProvider, useCart } from "../cart/CartContext";
import { ChapterCartModal } from "./ChapterCartModal";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1 }, isAuthenticated: true }),
}));

beforeEach(() => localStorage.clear());

// Renders the current cart contents so tests can assert exact mutations.
function CartProbe() {
  const { items } = useCart();
  return (
    <div data-testid="cart">
      {items.map((i) => `${i.type}:${i.id}`).sort().join(",")}
    </div>
  );
}

const cart = () => screen.getByTestId("cart").textContent;

const chapterFixture = () => ({
  id: 10,
  name: "Cell Injury",
  bundle_purchasable: true,
  bundle_price: "120.00",
  unlocked: false,
  notes: [
    { id: 100, title: "Sellable A", price: "40.00", is_free: false, unlocked: false },
    { id: 101, title: "Sellable B", price: "30.00", is_free: false, unlocked: false },
    { id: 102, title: "Free note", price: "0.00", is_free: true, unlocked: true },
    { id: 103, title: "Owned note", price: "50.00", is_free: false, unlocked: true },
    { id: 104, title: "Bundle-only", price: "0.00", is_free: false, unlocked: false },
  ],
});

function renderModal(chapter, { subjectId = 1, unitId = 2 } = {}) {
  render(
    <CartProvider>
      <CartProbe />
      <ChapterCartModal chapter={chapter} subjectId={subjectId} unitId={unitId} onClose={() => {}} />
    </CartProvider>
  );
}

describe("ChapterCartModal — note states", () => {
  it("shows Add only for individually-sellable, not-owned notes", () => {
    renderModal(chapterFixture());
    // The two sellable notes each get an "Add" pill.
    expect(screen.getAllByText("Add")).toHaveLength(2);
    // Owned / free notes are shown for context, without an add control.
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.getByText("Owned")).toBeInTheDocument();
    // The ₹0 non-free note is bundle-only.
    expect(screen.getByText("Included with chapter")).toBeInTheDocument();
  });

  it("adds a single note to the cart", () => {
    renderModal(chapterFixture());
    fireEvent.click(screen.getAllByText("Add")[0]); // Sellable A (id 100)
    expect(cart()).toBe("note:100");
  });

  it("adds all sellable notes, then removes them all", () => {
    renderModal(chapterFixture());
    fireEvent.click(screen.getByText("Add all 2"));
    expect(cart()).toBe("note:100,note:101"); // owned/free/bundle-only excluded
    fireEvent.click(screen.getByText("Remove all"));
    expect(cart()).toBe("");
  });
});

describe("ChapterCartModal — whole chapter + supersede", () => {
  it("adds the whole chapter to the cart", () => {
    renderModal(chapterFixture());
    fireEvent.click(screen.getByRole("button", { name: /Add · ₹120/ }));
    expect(cart()).toBe("chapter:10");
  });

  it("adding the whole chapter supersedes individually-added notes", () => {
    renderModal(chapterFixture());
    fireEvent.click(screen.getByText("Add all 2"));
    expect(cart()).toBe("note:100,note:101");
    fireEvent.click(screen.getByRole("button", { name: /Add · ₹120/ }));
    expect(cart()).toBe("chapter:10"); // the notes were removed
  });

  it("marks the sellable notes as included once the whole chapter is in the cart", () => {
    renderModal(chapterFixture());
    expect(screen.getAllByText("Included with chapter")).toHaveLength(1); // bundle-only only
    fireEvent.click(screen.getByRole("button", { name: /Add · ₹120/ }));
    // Now both sellable notes + the bundle-only note read "Included with chapter".
    expect(screen.getAllByText("Included with chapter")).toHaveLength(3);
    expect(screen.queryByText("Add all 2")).toBeNull();
  });
});

describe("ChapterCartModal — coverage & availability", () => {
  it("omits the whole-chapter option when the chapter isn't sold as a bundle", () => {
    const ch = chapterFixture();
    ch.bundle_purchasable = false;
    renderModal(ch);
    expect(screen.queryByRole("button", { name: /₹120/ })).toBeNull();
    // Individual notes are still addable.
    fireEvent.click(screen.getByText("Add all 2"));
    expect(cart()).toBe("note:100,note:101");
  });

  it("shows an 'already included' banner and no add controls when a parent unit is in the cart", () => {
    localStorage.setItem(
      "digikart_cart",
      JSON.stringify({ ownerId: 1, items: [{ type: "unit", id: 2 }] })
    );
    renderModal(chapterFixture(), { unitId: 2 });
    expect(screen.getByText(/already included in a bundle/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add · ₹120/ })).toBeNull();
    expect(screen.queryByText("Add all 2")).toBeNull();
    expect(screen.queryByText("Add")).toBeNull(); // no note add pills either
  });
});
