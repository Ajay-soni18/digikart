import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { CouponPromoOverlay } from "./CouponPromoOverlay";

const CODE = "HAPPYLEARNING50";

const auth = vi.hoisted(() => ({ current: { isAuthenticated: true, loading: false } }));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => auth.current }));

// The overlay opens on a timer and unlocks its controls on a second one, so
// every test drives fake timers. Fake timers also cover requestAnimationFrame,
// which is all the discount counter needs.
//
// NB: never call vi.unstubAllGlobals() here — test/setup.js installs the shared
// in-memory localStorage and matchMedia with vi.stubGlobal, and unstubbing would
// rip those out from under every following test.
beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  sessionStorage.clear();
  auth.current = { isAuthenticated: true, loading: false };
});

afterEach(() => {
  vi.useRealTimers();
  delete navigator.clipboard;
});

function renderOverlay(path = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CouponPromoOverlay />
    </MemoryRouter>
  );
}

/** Advance past the open delay only — controls are still locked. */
const openIt = () => act(() => void vi.advanceTimersByTime(700));
/** Advance past the full entrance sequence — ✕ and CTA are live. */
const finishAnimation = () => act(() => void vi.advanceTimersByTime(3000));

describe("CouponPromoOverlay", () => {
  it("stays hidden until the open delay elapses", () => {
    renderOverlay();
    expect(screen.queryByRole("dialog")).toBeNull();
    openIt();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows the coupon code and the offer terms", () => {
    renderOverlay();
    openIt();
    expect(screen.getByLabelText(`Copy coupon code ${CODE}`)).toBeInTheDocument();
    expect(screen.getByText(/on orders of ₹150 or more/i)).toBeInTheDocument();
  });

  it("reveals the close button only after the animation finishes", () => {
    renderOverlay();
    openIt();
    expect(screen.queryByLabelText("Close offer")).toBeNull();
    finishAnimation();
    expect(screen.getByLabelText("Close offer")).toBeInTheDocument();
  });

  it("closes on the cross button once revealed", () => {
    renderOverlay();
    openIt();
    finishAnimation();
    fireEvent.click(screen.getByLabelText("Close offer"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("ignores Esc mid-animation and honours it after the reveal", () => {
    renderOverlay();
    openIt();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    finishAnimation();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("copies the code to the clipboard when the code is clicked", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    // Scoped to this test (afterEach deletes it) — jsdom ships no clipboard.
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    renderOverlay();
    openIt();
    await act(async () => {
      fireEvent.click(screen.getByLabelText(`Copy coupon code ${CODE}`));
    });
    expect(writeText).toHaveBeenCalledWith(CODE);
    expect(screen.getByText(/copied/i)).toBeInTheDocument();
  });

  it("shows on the dashboard route only", () => {
    for (const path of ["/", "/login", "/signup", "/contact", "/admin", "/subjects/anatomy"]) {
      const { unmount } = renderOverlay(path);
      openIt();
      expect(screen.queryByRole("dialog")).toBeNull();
      unmount();
    }
  });

  it("does not show to a logged-out visitor on /dashboard", () => {
    auth.current = { isAuthenticated: false, loading: false };
    renderOverlay();
    openIt();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("waits for the auth bootstrap instead of skipping, then shows", () => {
    auth.current = { isAuthenticated: false, loading: true };
    const { rerender } = renderOverlay();
    openIt();
    expect(screen.queryByRole("dialog")).toBeNull();

    // Session verified → the overlay arms on the next render.
    auth.current = { isAuthenticated: true, loading: false };
    rerender(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <CouponPromoOverlay />
      </MemoryRouter>
    );
    openIt();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("only shows once, and remembers that in localStorage", () => {
    const first = renderOverlay();
    openIt();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    first.unmount();

    renderOverlay();
    openIt();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  /*
   * Regression: the flag used to live in sessionStorage, which is per-TAB — so a
   * new tab (or window, or browser restart) replayed the promo every time. It has
   * to persist beyond the tab session; sessionStorage being empty must not be
   * enough to re-arm it.
   */
  it("stays closed in a fresh tab session (flag is not tab-scoped)", () => {
    renderOverlay();
    openIt();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(localStorage.getItem("digikart_promo_seen_HAPPYLEARNING50")).toBe("1");

    cleanup();
    sessionStorage.clear(); // what a brand-new tab starts with
    renderOverlay();
    openIt();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
