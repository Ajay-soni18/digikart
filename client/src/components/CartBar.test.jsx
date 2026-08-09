import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CartProvider } from "../cart/CartContext";
import { CartBar } from "./CartBar";
import { paymentApi } from "../lib/paymentApi";

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
    renderBar({ authed: false, items: [{ type: "product", id: 1 }] });
    expect(screen.queryByText(/in cart/)).toBeNull();
  });

  it("renders nothing when the cart is empty", () => {
    renderBar({ authed: true, items: [] });
    expect(screen.queryByText(/in cart/)).toBeNull();
  });

  it("uses a singular label for one item", () => {
    renderBar({ items: [{ type: "bundle", id: 1 }] });
    expect(screen.getByText(/^1 item in cart$/)).toBeInTheDocument();
  });

  it("uses a plural label for multiple mixed items", () => {
    renderBar({ items: [{ type: "bundle", id: 1 }, { type: "product", id: 2 }] });
    expect(screen.getByText(/^2 items in cart$/)).toBeInTheDocument();
  });

  it("shows the server-computed total once the quote resolves", async () => {
    renderBar({ items: [{ type: "bundle", id: 1 }] });
    expect(await screen.findByText(/₹170/)).toBeInTheDocument();
  });

  it("empties the cart (and hides the bar) when Clear is clicked", () => {
    renderBar({ items: [{ type: "bundle", id: 1 }] });
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByText(/in cart/)).toBeNull();
  });
});

describe("CartBar — removing a single line at checkout", () => {
  const lines = [
    { type: "bundle", id: 9, label: "General Pathology — Unit (bundle)", price: "108.00", owned: false, covered: false },
    { type: "product", id: 1, label: "Systemic Pathology — Part 1", price: "59.00", owned: false, covered: false },
    { type: "product", id: 2, label: "Systemic Pathology — Part 2", price: "49.00", owned: false, covered: false },
  ];

  beforeEach(() => {
    paymentApi.quote.mockImplementation((items) => {
      const keep = lines.filter((l) =>
        (items || []).some((i) => i.type === l.type && i.id === l.id)
      );
      const total = keep.reduce((t, l) => t + Number(l.price), 0);
      return Promise.resolve({
        items: keep, subtotal: String(total), discount: "0", total: String(total), coupon: null,
      });
    });
  });

  async function openCheckout() {
    renderBar({ items: lines.map(({ type, id }) => ({ type, id })) });
    fireEvent.click(await screen.findByRole("button", { name: /checkout/i }));
    return screen.findByText("General Pathology — Unit (bundle)");
  }

  it("shows a remove control for every line", async () => {
    await openCheckout();
    expect(await screen.findAllByRole("button", { name: /remove .* from cart/i })).toHaveLength(3);
  });

  it("drops just that line and leaves the rest", async () => {
    await openCheckout();
    const buttons = await screen.findAllByRole("button", { name: /remove .* from cart/i });
    fireEvent.click(buttons[1]);
    await waitFor(() =>
      expect(screen.queryByText("Systemic Pathology — Part 1")).not.toBeInTheDocument()
    );
    expect(screen.getByText("General Pathology — Unit (bundle)")).toBeInTheDocument();
    expect(screen.getByText("Systemic Pathology — Part 2")).toBeInTheDocument();
  });

  it("re-quotes so the total drops", async () => {
    await openCheckout();
    // ₹216 shows twice — "Original price" and "Total payable".
    await waitFor(() => expect(screen.getAllByText("₹216").length).toBeGreaterThan(0));
    const buttons = await screen.findAllByRole("button", { name: /remove .* from cart/i });
    fireEvent.click(buttons[0]); // the ₹108 bundle
    await waitFor(() => expect(screen.getAllByText("₹108").length).toBeGreaterThan(0));
    expect(screen.queryByText("₹216")).not.toBeInTheDocument();
  });

  it("closes the modal when the last line is removed", async () => {
    await openCheckout();
    for (let i = 0; i < 3; i += 1) {
      const buttons = screen.queryAllByRole("button", { name: /remove .* from cart/i });
      if (!buttons.length) break;
      fireEvent.click(buttons[0]);
      await waitFor(() => {});
    }
    await waitFor(() => expect(screen.queryByText(/^Checkout$/)).not.toBeInTheDocument());
  });
});
