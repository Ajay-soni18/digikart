import { describe, it, expect } from "vitest";
import { money, chapterCost, unitPrice, subjectPrice } from "./pricing";

describe("money", () => {
  it("formats whole rupees with the ₹ symbol", () => {
    expect(money(100)).toBe("₹100");
    expect(money("249.00")).toBe("₹249");
    expect(money(0)).toBe("₹0");
  });
  it("rounds to the nearest whole rupee", () => {
    expect(money(99.6)).toBe("₹100");
    expect(money(99.4)).toBe("₹99");
  });
});

describe("chapterCost", () => {
  it("is 0 for a free chapter even if a bundle_price is set", () => {
    expect(chapterCost({ is_free: true, bundle_price: "500", notes: [] })).toBe(0);
  });
  it("uses bundle_price when present", () => {
    expect(chapterCost({ bundle_price: "150.00", notes: [{ price: "40" }] })).toBe(150);
  });
  it("sums note prices when there is no bundle_price, skipping free notes", () => {
    expect(
      chapterCost({
        bundle_price: null,
        notes: [
          { price: "60", is_free: false },
          { price: "40", is_free: false },
          { price: "0", is_free: true },
        ],
      })
    ).toBe(100);
  });
  it("tolerates a missing notes array", () => {
    expect(chapterCost({ bundle_price: null })).toBe(0);
  });
});

describe("unitPrice", () => {
  it("uses bundle_price when present", () => {
    expect(unitPrice({ bundle_price: "199.00", chapters: [] })).toBe(199);
  });
  it("sums chapter costs otherwise", () => {
    expect(
      unitPrice({ bundle_price: null, chapters: [{ bundle_price: "50" }, { bundle_price: "70" }] })
    ).toBe(120);
  });
});

describe("subjectPrice", () => {
  it("uses bundle_price when present", () => {
    expect(subjectPrice({ bundle_price: "400", units: [] })).toBe(400);
  });
  it("sums unit prices (which roll up chapters) otherwise", () => {
    expect(
      subjectPrice({
        bundle_price: null,
        units: [
          { bundle_price: "100" },
          { bundle_price: null, chapters: [{ bundle_price: "30" }, { bundle_price: "20" }] },
        ],
      })
    ).toBe(150);
  });
});
