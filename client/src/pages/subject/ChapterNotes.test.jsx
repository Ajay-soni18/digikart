import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { CartProvider, useCart } from "../../cart/CartContext";
import ChapterNotes from "./ChapterNotes";

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1 }, isAuthenticated: true }),
}));
vi.mock("../../lib/api", () => ({ api: { get: vi.fn() } }));

import { api } from "../../lib/api";

const makeData = () => ({
  chapter: {
    id: 100,
    name: "Cell Injury",
    subject: "Pathology",
    is_free: false,
    bundle_purchasable: true,
    bundle_price: "100.00",
    unlocked: false,
  },
  notes: [
    { id: 1000, title: "Sellable", price: "40.00", is_free: false, unlocked: false },
    { id: 1001, title: "Freebie", price: "0.00", is_free: true, unlocked: true },
    { id: 1002, title: "Owned", price: "50.00", is_free: false, unlocked: true },
    { id: 1003, title: "Bundle-only", price: "0.00", is_free: false, unlocked: false },
  ],
});

beforeEach(() => {
  localStorage.clear();
  api.get.mockResolvedValue({ data: makeData() });
});

function CartProbe() {
  const { items } = useCart();
  return <div data-testid="cart">{items.map((i) => `${i.type}:${i.id}`).sort().join(",")}</div>;
}
const cart = () => screen.getByTestId("cart").textContent;

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/subjects/patho/chapters/100/notes"]}>
      <CartProvider>
        <CartProbe />
        <Routes>
          <Route path="/subjects/:slug/chapters/:chapterId/notes" element={<ChapterNotes />} />
        </Routes>
      </CartProvider>
    </MemoryRouter>
  );
}

describe("ChapterNotes page", () => {
  it("renders the chapter CTA and the correct per-note controls", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: /Add · ₹100/ })).toBeInTheDocument();
    expect(screen.getAllByText("Add")).toHaveLength(1); // only the sellable note
    expect(screen.getAllByText("Read")).toHaveLength(2); // free + owned notes
    expect(screen.getByText("Included with chapter")).toBeInTheDocument(); // bundle-only note
    expect(screen.getByText("Free")).toBeInTheDocument();
  });

  it("adds an individual note to the cart", async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Add"));
    expect(cart()).toBe("note:1000");
  });

  it("adds the whole chapter and marks its notes as included", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Add · ₹100/ }));
    expect(cart()).toBe("chapter:100");
    expect(screen.getByRole("button", { name: /Added to cart/ })).toBeInTheDocument();
    // Sellable note is now superseded → shown as included, no Add pill.
    expect(screen.queryByText("Add")).toBeNull();
    expect(screen.getAllByText("Included with chapter").length).toBe(2);
  });

  it("adding the whole chapter supersedes a note already in the cart", async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Add")); // note 1000
    expect(cart()).toBe("note:1000");
    fireEvent.click(screen.getByRole("button", { name: /Add · ₹100/ }));
    expect(cart()).toBe("chapter:100");
  });
});
