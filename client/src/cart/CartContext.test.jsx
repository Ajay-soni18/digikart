import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { CartProvider, useCart } from "./CartContext";

// Mutable mocked auth so we can simulate account changes / logout.
const auth = vi.hoisted(() => ({ current: { user: { id: 1 }, isAuthenticated: true } }));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => auth.current }));

beforeEach(() => {
  localStorage.clear();
  auth.current = { user: { id: 1 }, isAuthenticated: true };
});

const setup = () => renderHook(() => useCart(), { wrapper: CartProvider });

describe("keying by (type, id)", () => {
  it("treats a product and a bundle with the same id as distinct items", () => {
    const { result } = setup();
    act(() => result.current.add("product", 5));
    expect(result.current.has("product", 5)).toBe(true);
    expect(result.current.has("bundle", 5)).toBe(false);
    act(() => result.current.add("bundle", 5));
    expect(result.current.has("bundle", 5)).toBe(true);
    expect(result.current.count).toBe(2);
  });

  it("add is idempotent (no duplicates)", () => {
    const { result } = setup();
    act(() => {
      result.current.add("product", 1);
      result.current.add("product", 1);
    });
    expect(result.current.count).toBe(1);
  });

  it("toggle adds then removes the same pair", () => {
    const { result } = setup();
    act(() => result.current.toggle("bundle", 7));
    expect(result.current.has("bundle", 7)).toBe(true);
    act(() => result.current.toggle("bundle", 7));
    expect(result.current.has("bundle", 7)).toBe(false);
  });

  it("remove targets only the exact (type, id) pair", () => {
    const { result } = setup();
    act(() => {
      result.current.add("product", 1);
      result.current.add("bundle", 1);
    });
    act(() => result.current.remove("product", 1));
    expect(result.current.has("product", 1)).toBe(false);
    expect(result.current.has("bundle", 1)).toBe(true);
  });

  it("removeMany drops a batch of pairs (the supersede mechanism)", () => {
    const { result } = setup();
    act(() => {
      result.current.add("product", 1);
      result.current.add("product", 2);
      result.current.add("bundle", 9);
    });
    act(() => result.current.removeMany([{ type: "product", id: 1 }, { type: "product", id: 2 }]));
    expect(result.current.has("product", 1)).toBe(false);
    expect(result.current.has("product", 2)).toBe(false);
    expect(result.current.has("bundle", 9)).toBe(true);
    expect(result.current.count).toBe(1);
  });

  it("clear empties the cart", () => {
    const { result } = setup();
    act(() => {
      result.current.add("bundle", 1);
      result.current.clear();
    });
    expect(result.current.count).toBe(0);
  });
});

describe("persistence", () => {
  it("mirrors items to localStorage", () => {
    const { result } = setup();
    act(() => result.current.add("bundle", 3));
    const stored = JSON.parse(localStorage.getItem("digikart_cart"));
    expect(stored.items).toContainEqual({ type: "bundle", id: 3 });
  });

  it("rehydrates only well-formed items, coerces numeric ids, and de-dupes", () => {
    localStorage.setItem(
      "digikart_cart",
      JSON.stringify({
        ownerId: 1,
        items: [
          { type: "product", id: 1 },
          { type: "product", id: "2" }, // numeric string is coerced
          { type: "bogus", id: 3 }, // invalid type dropped
          { type: "bundle" }, // missing id dropped
          { type: "product", id: 1 }, // duplicate dropped
        ],
      })
    );
    const { result } = setup();
    expect(result.current.items).toEqual([
      { type: "product", id: 1 },
      { type: "product", id: 2 },
    ]);
  });
});

describe("user binding", () => {
  it("clears the cart when a different account signs in on the same device", () => {
    localStorage.setItem(
      "digikart_cart",
      JSON.stringify({ ownerId: 1, items: [{ type: "product", id: 1 }] })
    );
    const { result, rerender } = setup();
    expect(result.current.count).toBe(1);
    auth.current = { user: { id: 2 }, isAuthenticated: true };
    act(() => rerender());
    expect(result.current.count).toBe(0);
  });

  it("clears the cart on logout", () => {
    const { result, rerender } = setup();
    act(() => result.current.add("product", 1));
    expect(result.current.count).toBe(1);
    auth.current = { user: null, isAuthenticated: false };
    act(() => rerender());
    expect(result.current.count).toBe(0);
  });
});
