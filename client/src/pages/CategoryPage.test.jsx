import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { CartProvider, useCart } from "../cart/CartContext";
import CategoryPage from "./CategoryPage";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1 }, isAuthenticated: true }),
}));
vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

import { api } from "../lib/api";

const makeData = () => ({
  id: 5,
  slug: "pathology",
  name: "Pathology",
  description: "",
  path: "Medicine · Pathology",
  is_coming_soon: false,
  breadcrumb: [{ slug: "medicine", name: "Medicine" }],
  children: [{ id: 7, slug: "sub", name: "Subcategory", product_count: 3 }],
  products: [
    { id: 1, slug: "sellable", title: "Sellable", price: "40.00", is_free: false, unlocked: false, is_coming_soon: false, file_count: 1 },
    { id: 2, slug: "freebie", title: "Freebie", price: "0.00", is_free: true, unlocked: true, is_coming_soon: false, file_count: 1 },
    { id: 3, slug: "owned", title: "Owned", price: "50.00", is_free: false, unlocked: true, is_coming_soon: false, file_count: 2 },
    { id: 4, slug: "soon", title: "Soon", price: "10.00", is_free: false, unlocked: false, is_coming_soon: true, file_count: 0 },
  ],
  bundles: [
    { id: 9, slug: "everything", title: "Everything", price: "99.00", product_count: 3, unlocked: false, is_coming_soon: false },
  ],
});

beforeEach(() => {
  localStorage.clear();
  api.get.mockResolvedValue({ data: makeData() });
});

function CartProbe() {
  const { items } = useCart();
  return (
    <div data-testid="cart">
      {items.map((i) => `${i.type}:${i.id}`).sort().join(",")}
    </div>
  );
}
const cart = () => screen.getByTestId("cart").textContent;

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/c/pathology"]}>
      <CartProvider>
        <CartProbe />
        <Routes>
          <Route path="/c/:slug" element={<CategoryPage />} />
        </Routes>
      </CartProvider>
    </MemoryRouter>
  );
}

describe("CategoryPage", () => {
  it("renders the breadcrumb, children, bundles and products", async () => {
    renderPage();
    expect(await screen.findByText("Pathology")).toBeInTheDocument();
    expect(screen.getByText("Medicine")).toBeInTheDocument();
    expect(screen.getByText("Subcategory")).toBeInTheDocument();
    expect(screen.getByText("Everything")).toBeInTheDocument();
    expect(screen.getByText("Sellable")).toBeInTheDocument();
  });

  it("shows a buy control only for the sellable product", async () => {
    renderPage();
    await screen.findByText("Sellable");
    // "Owned" and the free product must not offer an Add button.
    expect(screen.getAllByRole("button", { name: /add$/i })).toHaveLength(1);
    expect(screen.getAllByText(/Owned/).length).toBeGreaterThan(0);
  });

  it("adds a product to the cart as type product", async () => {
    renderPage();
    await screen.findByText("Sellable");
    fireEvent.click(screen.getByRole("button", { name: /add$/i }));
    await waitFor(() => expect(cart()).toBe("product:1"));
  });

  it("adds a bundle to the cart as type bundle", async () => {
    renderPage();
    await screen.findByText("Everything");
    fireEvent.click(screen.getByRole("button", { name: /add bundle/i }));
    await waitFor(() => expect(cart()).toBe("bundle:9"));
  });

  it("marks products as covered once a bundle is in the cart", async () => {
    renderPage();
    await screen.findByText("Everything");
    fireEvent.click(screen.getByRole("button", { name: /add bundle/i }));
    // The sellable product's Add button is replaced by the covered label.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /add$/i })).not.toBeInTheDocument()
    );
    expect(screen.getByText(/in your bundle/i)).toBeInTheDocument();
  });

  it("surfaces a friendly error when the category fails to load", async () => {
    api.get.mockRejectedValueOnce(new Error("boom"));
    renderPage();
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
  });
});

describe("CategoryPage — unbuyable bundles", () => {
  it("offers no Add button for a bundle the server marks unpurchasable", async () => {
    const data = makeData();
    data.bundles = [
      { id: 9, slug: "empty", title: "Nothing Inside", price: "0.00",
        product_count: 0, unlocked: false, is_coming_soon: false, purchasable: false },
    ];
    api.get.mockResolvedValue({ data });
    renderPage();
    await screen.findByText("Nothing Inside");
    expect(screen.queryByRole("button", { name: /add bundle/i })).not.toBeInTheDocument();
    expect(screen.getByText(/nothing to buy yet/i)).toBeInTheDocument();
  });

  it("still offers a purchasable bundle", async () => {
    const data = makeData();
    data.bundles[0].purchasable = true;
    api.get.mockResolvedValue({ data });
    renderPage();
    await screen.findByText("Everything");
    expect(screen.getByRole("button", { name: /add bundle/i })).toBeInTheDocument();
  });
});

describe("CategoryPage — removing from the cart", () => {
  it("takes a product back out when its button is clicked again", async () => {
    renderPage();
    await screen.findByText("Sellable");
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    await waitFor(() => expect(cart()).toBe("product:1"));
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));
    await waitFor(() => expect(cart()).toBe(""));
  });

  it("takes a bundle back out too", async () => {
    renderPage();
    await screen.findByText("Everything");
    fireEvent.click(screen.getByRole("button", { name: /add bundle/i }));
    await waitFor(() => expect(cart()).toBe("bundle:9"));
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));
    await waitFor(() => expect(cart()).toBe(""));
  });

  it("restores the product's own Add button once the covering bundle is removed", async () => {
    renderPage();
    await screen.findByText("Everything");
    fireEvent.click(screen.getByRole("button", { name: /add bundle/i }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /^add$/i })).not.toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^add$/i })).toBeInTheDocument()
    );
  });
});
