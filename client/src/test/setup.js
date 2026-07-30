// Vitest setup: jest-dom matchers, React cleanup, and a deterministic
// localStorage. Everything is in-memory and local — no network, no database.
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// Node's experimental Web Storage global can shadow jsdom's localStorage and
// needs a backing file, which breaks it under the test runner. Install a plain
// in-memory Storage so the app's persistence (CartContext) and the tests share
// one consistent store.
function makeMemoryStorage() {
  const store = new Map();
  return {
    clear: () => store.clear(),
    getItem: (k) => (store.has(String(k)) ? store.get(String(k)) : null),
    setItem: (k, v) => store.set(String(k), String(v)),
    removeItem: (k) => store.delete(String(k)),
    key: (i) => Array.from(store.keys())[i] ?? null,
    get length() {
      return store.size;
    },
  };
}

vi.stubGlobal("localStorage", makeMemoryStorage());

// jsdom doesn't implement matchMedia; the app header / theme code reads it.
vi.stubGlobal("matchMedia", (query) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
}));

afterEach(() => {
  cleanup();
});
