import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Test-only config, separate from vite.config.js so it never affects the build.
// Everything runs locally in a jsdom sandbox — no network, no database.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    include: ["src/**/*.test.{js,jsx}"],
    css: false,
    restoreMocks: true,
    clearMocks: true,
  },
});
