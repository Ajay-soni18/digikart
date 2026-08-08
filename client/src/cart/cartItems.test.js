import { describe, expect, it } from "vitest";
import {
  bundleDescendantPairs,
  cartKey,
  isProductSellable,
  productPairs,
  productRowState,
  sellableProducts,
} from "./cartItems";

const product = (over = {}) => ({
  id: 1,
  price: "49.00",
  is_free: false,
  unlocked: false,
  is_coming_soon: false,
  ...over,
});

describe("cartKey", () => {
  it("keeps product and bundle ids from colliding", () => {
    expect(cartKey("product", 3)).not.toBe(cartKey("bundle", 3));
  });
});

describe("productPairs", () => {
  it("maps products to cart pairs", () => {
    expect(productPairs([{ id: 1 }, { id: 2 }])).toEqual([
      { type: "product", id: 1 },
      { type: "product", id: 2 },
    ]);
  });
  it("tolerates a missing list", () => {
    expect(productPairs(undefined)).toEqual([]);
  });
});

describe("bundleDescendantPairs", () => {
  it("lists member products and nested bundles", () => {
    expect(
      bundleDescendantPairs({ products: [{ id: 1 }], bundles: [{ id: 9 }] })
    ).toEqual([
      { type: "product", id: 1 },
      { type: "bundle", id: 9 },
    ]);
  });
});

describe("isProductSellable", () => {
  it("is true for a locked, priced, non-free product", () => {
    expect(isProductSellable(product())).toBe(true);
  });
  it("is false once owned", () => {
    expect(isProductSellable(product({ unlocked: true }))).toBe(false);
  });
  it("is false when free", () => {
    expect(isProductSellable(product({ is_free: true }))).toBe(false);
  });
  it("is false at zero price (bundle-only)", () => {
    expect(isProductSellable(product({ price: "0.00" }))).toBe(false);
  });
});

describe("sellableProducts", () => {
  it("keeps only the ones that can be bought alone", () => {
    const list = [product({ id: 1 }), product({ id: 2, is_free: true })];
    expect(sellableProducts(list).map((p) => p.id)).toEqual([1]);
  });
});

describe("productRowState", () => {
  it("flags coming-soon before anything else", () => {
    expect(productRowState(product({ is_coming_soon: true, unlocked: true }))).toBe(
      "coming_soon"
    );
  });
  it("reports owned products", () => {
    expect(productRowState(product({ unlocked: true }))).toBe("owned");
  });
  it("reports covered when a containing bundle is in the cart", () => {
    expect(productRowState(product(), { coveringBundleInCart: true })).toBe("covered");
  });
  it("reports buyable for a sellable product", () => {
    expect(productRowState(product())).toBe("buyable");
  });
  it("reports free for a free product", () => {
    expect(productRowState(product({ is_free: true }))).toBe("free");
  });
  it("reports free for a bundle-only product with no standalone price", () => {
    expect(productRowState(product({ price: "0.00" }))).toBe("free");
  });
});
