import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { CartProvider, useCart } from "../cart/CartContext";
import ProductPage from "./ProductPage";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1 }, isAuthenticated: true }),
}));
vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));
// The viewer pulls in pdf.js, which jsdom can't run and this page's tests
// don't need — the locked/unlocked decision is what matters here.
vi.mock("./FileViewer", () => ({
  FileViewer: ({ file }) => <div data-testid="viewer">viewing {file.title}</div>,
}));

import { api } from "../lib/api";

const makeProduct = (over = {}) => ({
  id: 1,
  slug: "moody-pack",
  title: "Moody Pack",
  description: "Ten presets",
  price: "299.00",
  is_free: false,
  purchasable: true,
  unlocked: false,
  is_coming_soon: false,
  youtube_video_id: "abcdefghijk",
  youtube_url: "https://youtu.be/abcdefghijk",
  file_count: 2,
  category: { id: 3, slug: "photography", name: "Photography", path: "Creative · Photography" },
  files: [
    { id: 11, title: "presets.zip", delivery: "download", file_type: "archive", size_bytes: 2400000, version: "v1" },
    { id: 12, title: "guide.pdf", delivery: "protected", file_type: "pdf", page_count: 12, version: "v1" },
  ],
  in_bundles: [
    { id: 9, slug: "everything", title: "Everything", price: "999.00", product_count: 4, unlocked: false },
  ],
  ...over,
});

beforeEach(() => {
  localStorage.clear();
  api.get.mockResolvedValue({ data: makeProduct() });
});

function CartProbe() {
  const { items } = useCart();
  return <div data-testid="cart">{items.map((i) => `${i.type}:${i.id}`).sort().join(",")}</div>;
}
const cart = () => screen.getByTestId("cart").textContent;

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/p/moody-pack"]}>
      <CartProvider>
        <CartProbe />
        <Routes>
          <Route path="/p/:slug" element={<ProductPage />} />
        </Routes>
      </CartProvider>
    </MemoryRouter>
  );
}

describe("ProductPage", () => {
  it("shows the product, its files and its price", async () => {
    renderPage();
    expect(await screen.findByText("Moody Pack")).toBeInTheDocument();
    expect(screen.getByText("presets.zip")).toBeInTheDocument();
    expect(screen.getByText("guide.pdf")).toBeInTheDocument();
    expect(screen.getByText("₹299")).toBeInTheDocument();
  });

  it("plays the YouTube hook even though the product is locked", async () => {
    renderPage();
    await screen.findByText("Moody Pack");
    const frame = document.querySelector("iframe");
    expect(frame).toBeTruthy();
    expect(frame.getAttribute("src")).toContain("abcdefghijk");
  });

  it("locks every file until the product is owned", async () => {
    renderPage();
    await screen.findByText("Moody Pack");
    expect(screen.getAllByText(/locked/i)).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /read|download/i })).not.toBeInTheDocument();
  });

  it("offers Read and Download once owned", async () => {
    api.get.mockResolvedValue({ data: makeProduct({ unlocked: true }) });
    renderPage();
    await screen.findByText("Moody Pack");
    expect(screen.getByRole("button", { name: /read/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
  });

  it("opens the protected viewer for a protected file", async () => {
    api.get.mockResolvedValue({ data: makeProduct({ unlocked: true }) });
    renderPage();
    await screen.findByText("Moody Pack");
    fireEvent.click(screen.getByRole("button", { name: /read/i }));
    expect(await screen.findByTestId("viewer")).toHaveTextContent("guide.pdf");
  });

  it("adds the product to the cart", async () => {
    renderPage();
    await screen.findByText("Moody Pack");
    fireEvent.click(screen.getByRole("button", { name: /add to cart/i }));
    await waitFor(() => expect(cart()).toBe("product:1"));
  });

  it("offers the containing bundle as an alternative", async () => {
    renderPage();
    await screen.findByText("Moody Pack");
    fireEvent.click(screen.getByRole("button", { name: /add bundle/i }));
    await waitFor(() => expect(cart()).toBe("bundle:9"));
  });

  it("hides the bundle upsell once the product is owned", async () => {
    api.get.mockResolvedValue({ data: makeProduct({ unlocked: true }) });
    renderPage();
    await screen.findByText("Moody Pack");
    expect(screen.queryByRole("button", { name: /add bundle/i })).not.toBeInTheDocument();
  });

  it("says so when a product only sells inside a bundle", async () => {
    api.get.mockResolvedValue({
      data: makeProduct({ purchasable: false, price: "0.00" }),
    });
    renderPage();
    expect(await screen.findByText(/sold as part of a bundle/i)).toBeInTheDocument();
  });
});
