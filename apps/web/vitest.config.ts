import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// tsconfig keeps `jsx: preserve` for Next, so component tests need their own JSX transform; the
// `@/` alias comes from tsconfig paths. `server-only` throws outside Next's server bundle, so tests
// get an empty stub.
export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
  resolve: {
    tsconfigPaths: true,
    alias: {
      "server-only": fileURLToPath(new URL("./src/test/server-only-stub.ts", import.meta.url)),
    },
  },
});
