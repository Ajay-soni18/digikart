import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { CartProvider, useCart } from "../../cart/CartContext";
import { NotesSection } from "./SubjectPage";

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1 }, isAuthenticated: true }),
}));

beforeEach(() => localStorage.clear());

function CartProbe() {
  const { items } = useCart();
  return <div data-testid="cart">{items.map((i) => `${i.type}:${i.id}`).sort().join(",")}</div>;
}

const cart = () => screen.getByTestId("cart").textContent;

const makeSubject = () => ({
  id: 1,
  name: "Pathology",
  slug: "pathology",
  bundle_purchasable: true,
  bundle_price: "400.00",
  units: [
    {
      id: 10,
      name: "Unit A",
      is_coming_soon: false,
      bundle_purchasable: true,
      bundle_price: "200.00",
      chapters: [
        {
          id: 100,
          name: "Buyable Ch",
          is_coming_soon: false,
          unlocked: false,
          bundle_purchasable: true,
          bundle_price: "100.00",
          notes: [
            { id: 1000, title: "n1", price: "40.00", is_free: false, unlocked: false },
            { id: 1001, title: "free", price: "0.00", is_free: true, unlocked: true },
          ],
        },
        { id: 101, name: "Owned Ch", is_coming_soon: false, unlocked: true, bundle_purchasable: true, bundle_price: "50.00", notes: [] },
        { id: 102, name: "Soon Ch", is_coming_soon: true, unlocked: false, bundle_purchasable: false, notes: [] },
        {
          id: 103,
          name: "Free-only Ch",
          is_coming_soon: false,
          unlocked: false,
          bundle_purchasable: false,
          notes: [{ id: 1030, title: "freebie", price: "0.00", is_free: true, unlocked: true }],
        },
      ],
    },
  ],
});

function renderSection(subject = makeSubject(), { seed } = {}) {
  if (seed) localStorage.setItem("digikart_cart", JSON.stringify({ ownerId: 1, items: seed }));
  render(
    <MemoryRouter>
      <CartProvider>
        <CartProbe />
        <NotesSection subject={subject} />
      </CartProvider>
    </MemoryRouter>
  );
}

describe("NotesSection — banners & chapter rows", () => {
  it("shows the subject and unit bundle add-to-cart CTAs with server-agnostic prices", () => {
    renderSection();
    expect(screen.getByRole("button", { name: /Add to cart · ₹400/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add · ₹200/ })).toBeInTheDocument();
  });

  it("renders exactly one Add-to-cart chapter button (only the buyable chapter)", () => {
    renderSection();
    expect(screen.getAllByRole("button", { name: "Add to cart" })).toHaveLength(1);
    expect(screen.getByText("Buyable Ch")).toBeInTheDocument();
    expect(screen.getByText("Owned Ch")).toBeInTheDocument();
    expect(screen.getByText("Unlocked")).toBeInTheDocument(); // owned chapter subtitle
    expect(screen.getByText("Soon Ch")).toBeInTheDocument(); // coming soon, no button
    expect(screen.getByText("Free-only Ch")).toBeInTheDocument(); // plain link, no button
  });

  it("opens the chapter modal when a chapter's Add-to-cart is clicked", () => {
    renderSection();
    expect(screen.queryByText("Complete chapter")).toBeNull(); // modal closed
    fireEvent.click(screen.getByRole("button", { name: "Add to cart" }));
    // Modal is open: its unique "Complete chapter" CTA + the chapter's note count appear.
    expect(screen.getByText("Complete chapter")).toBeInTheDocument();
    expect(screen.getByText(/2 notes in this chapter/i)).toBeInTheDocument();
  });
});

describe("NotesSection — bundle add + supersede", () => {
  it("adds the whole subject to the cart and supersedes its descendants already in the cart", () => {
    renderSection(makeSubject(), { seed: [{ type: "chapter", id: 100 }, { type: "note", id: 1000 }] });
    expect(cart()).toBe("chapter:100,note:1000");
    fireEvent.click(screen.getByRole("button", { name: /Add to cart · ₹400/ }));
    expect(cart()).toBe("subject:1"); // chapter + note removed
    expect(screen.getByRole("button", { name: /Added to cart/ })).toBeInTheDocument();
  });

  it("adds the whole unit and supersedes its chapters/notes", () => {
    renderSection(makeSubject(), { seed: [{ type: "chapter", id: 100 }, { type: "note", id: 1000 }] });
    fireEvent.click(screen.getByRole("button", { name: /Add · ₹200/ }));
    expect(cart()).toBe("unit:10");
  });
});

describe("NotesSection — covered by a bundle already in the cart", () => {
  it("marks the unit and chapters as included when the subject is in the cart", () => {
    renderSection(makeSubject(), { seed: [{ type: "subject", id: 1 }] });
    // Subject CTA reflects it's added; unit buy button is replaced by an included note.
    expect(screen.getByRole("button", { name: /Added to cart/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add · ₹200/ })).toBeNull();
    expect(screen.getByText(/included in the subject bundle/i)).toBeInTheDocument();
    // The buyable chapter now shows as covered, with no Add-to-cart button.
    expect(screen.getAllByText("Included in your cart bundle").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole("button", { name: "Add to cart" })).toBeNull();
  });
});
