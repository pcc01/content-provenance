import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Review Shell — replaces the old static frontend/index.html dashboard.
// In dev, run this alongside `uvicorn app.main:app` (proxy below forwards
// API calls) and demo-target's own dev server (5174), which this app iframes.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 8001, not 8000 — this machine also runs another project's stack on
      // 8000/5432/6379/3000/9090; see docker-compose.yml's port comment.
      "/api": { target: "http://localhost:8001", changeOrigin: true },
      // Phase 8's fetch+rewrite pages inject <script src="/sdk-dist/
      // overlay.js">, resolved root-relative to whatever origin served
      // them (this dev server) — proxy it same as /api so that resolves
      // to the backend's static mount instead of 404ing against Vite.
      // NOT /review-sdk: that prefix is the Review Shell's own .ts source
      // (Vite's own dev-transform serves it) — proxying it too would
      // shadow those legitimate requests, which is exactly what broke.
      "/sdk-dist": { target: "http://localhost:8001", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
  },
});
