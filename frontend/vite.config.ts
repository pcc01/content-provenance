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
    },
  },
  build: {
    outDir: "dist",
  },
});
