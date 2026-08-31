import react from "@vitejs/plugin-react";
import { configDefaults, coverageConfigDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // Extend Vitest's default test-file exclusions rather than replace them -- the previous
    // list ("node_modules/**", ".next/**", "e2e/**") had no "**/" prefix, so it only matched
    // those directories at the project root, not nested occurrences.
    exclude: [...configDefaults.exclude, "**/.next/**", "**/e2e/**"],
    coverage: {
      reporter: ["text", "json-summary", "json"],
      // Vitest 4 dropped `coverage.all`, so without an explicit `include`, coverage only
      // measures files a test actually imports -- an entirely untested source file
      // contributes nothing to the denominator instead of counting as uncovered, which
      // silently defeats the coverage ratchet (see root CLAUDE.md).
      include: ["app/**/*.{ts,tsx}", "middleware.ts"],
      exclude: [...coverageConfigDefaults.exclude, "**/.next/**", "**/e2e/**"],
    },
  },
});
