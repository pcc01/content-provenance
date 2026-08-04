import { defineConfig } from "vite";
import { resolve } from "node:path";

// Bundles overlay.ts into a single dependency-free browser script. Needed
// for Phase 8: the fetch+rewrite loader serves plain rewritten HTML
// directly from FastAPI (no Vite dev-transform in the response path), so
// the SDK has to exist as real, already-compiled JS on disk rather than
// relying on Vite transforming a .ts import at request time the way the
// React apps (frontend/src, demo-target) already do.
export default defineConfig({
  build: {
    outDir: resolve(__dirname, "dist"),
    emptyOutDir: true,
    lib: {
      entry: resolve(__dirname, "overlay.ts"),
      name: "ReviewSDK",
      formats: ["iife"],
      fileName: () => "overlay.js",
    },
  },
});
