import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CartProvider } from "../cart/CartContext";
import { CartBar } from "./CartBar";

const auth = vi.hoisted(() => ({ current: { user: { id: 1 }, isAuthenticated: true } }));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => auth.current }));
vi.mock("../lib/paymentApi", () => ({
  paymentApi: { quote: vi.fn(() => Promise.resolve({ total: "170", items: [] })) },
}));

beforeEach(() => {
  localStorage.clear();
  auth.current = { user: { id: 1 }, isAuthenticated: true };
});

function renderBar({ items = [], authed = true } = {}) {
  auth.current = { user: authed ? { id: 1 } : null, isAuthenticated: authed };
  if (items.length) localStorage.setItem("digikart_cart", JSON.stringify({ ownerId: 1, items }));
  render(
    <CartProvider>
      <CartBar />
    </CartProvider>
  );
}

describe("CartBar", () => {
  it("renders nothing when the user is not authenticated", () => {
    renderBar({ authed: false, items: [{ type: "note", id: 1 }] });
    expect(screen.queryByText(/in cart/)).toBeNull();
  });

  it("renders nothing when the cart is empty", () => {
    renderBar({ authed: true, items: [] });
    expect(screen.queryByText(/in cart/)).toBeNull();
  });

  it("uses a singular label for one item", () => {
    renderBar({ items: [{ type: "chapter", id: 1 }] });
    expect(screen.getByText(/^1 item in cart$/)).toBeInTheDocument();
  });

  it("uses a plural label for multiple mixed items", () => {
    renderBar({ items: [{ type: "chapter", id: 1 }, { type: "note", id: 2 }] });
    expect(screen.getByText(/^2 items in cart$/)).toBeInTheDocument();
  });

  it("shows the server-computed total once the quote resolves", async () => {
    renderBar({ items: [{ type: "chapter", id: 1 }] });
    expect(await screen.findByText(/₹170/)).toBeInTheDocument();
  });

  it("empties the cart (and hides the bar) when Clear is clicked", () => {
    renderBar({ items: [{ type: "chapter", id: 1 }] });
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByText(/in cart/)).toBeNull();
  });
});
