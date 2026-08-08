import { describe, expect, it } from "vitest";
import { lineCost, money, payableTotal, productCost } from "./pricing";

describe("money", () => {
  it("formats whole rupees", () => {
    expect(money(299)).toBe("₹299");
    expect(money("49.50")).toBe("₹50");
  });
  it("treats missing values as zero", () => {
    expect(money(undefined)).toBe("₹0");
  });
});

describe("productCost", () => {
  it("is the price of a paid product", () => {
    expect(productCost({ price: "49.00", is_free: false })).toBe(49);
  });
  it("is zero for a free product, whatever price it carries", () => {
    expect(productCost({ price: "49.00", is_free: true })).toBe(0);
  });
});

describe("payableTotal", () => {
  it("adds up the lines that must be paid for", () => {
    expect(
      payableTotal([
        { price: "100.00" },
        { price: "40.00" },
      ])
    ).toBe(140);
  });

  it("skips lines already owned", () => {
    expect(
      payableTotal([
        { price: "100.00", owned: true },
        { price: "40.00" },
      ])
    ).toBe(40);
  });

  it("skips lines covered by a bundle in the same cart", () => {
    expect(
      payableTotal([
        { price: "100.00" },
        { price: "40.00", covered: true },
      ])
    ).toBe(100);
  });

  it("is zero for an empty cart", () => {
    expect(payableTotal([])).toBe(0);
  });
});

describe("lineCost", () => {
  it("reads whatever the server priced the line at", () => {
    expect(lineCost({ price: "60.00" })).toBe(60);
    expect(lineCost({})).toBe(0);
  });
});
