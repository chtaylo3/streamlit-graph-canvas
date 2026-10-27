import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Kept separate from vite.config.ts so tests run against React's development
// build (required by act()) instead of the production define used for bundling.
// DOM tests opt in per file with `// @vitest-environment happy-dom`.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/**/*.d.ts"],
      reporter: ["text-summary", "text"],
      // A ratchet just below current coverage; raise it as coverage grows.
      // index.tsx is exercised by the Playwright suite rather than here.
      thresholds: {
        lines: 60,
        branches: 57,
      },
    },
  },
});
