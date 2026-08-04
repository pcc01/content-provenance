import { defineConfig } from "vite";
import { resolve } from "node:path";

// Bundles harvest.ts into a single dependency-free browser script — the
// same DOM-walking logic Phase 8's Playwright path and Phase 10's browser
// extension both need, compiled once so they can't drift apart. Shares
// dist/ with vite.sdk.config.ts's overlay.js build; emptyOutDir is off
// here since that build already cleared dist/ once at the start of the
// `build:sdk` script chain — this one must not wipe its sibling's output.
export default defineConfig({
  build: {
    outDir: resolve(__dirname, "dist"),
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, "harvest.ts"),
      name: "ReviewHarvest",
      formats: ["iife"],
      fileName: () => "harvest.js",
    },
  },
});
