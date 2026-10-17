import { defineConfig } from "vitest/config";

// tsconfig keeps `jsx: preserve` for Next, so component tests need their own JSX transform; the
// `@/` alias comes from tsconfig paths.
export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
  resolve: { tsconfigPaths: true },
});
