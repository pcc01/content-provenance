import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Demo target app — a minimal stand-in "content site" the Review Shell can
// iframe. Runs on its own dev server (5174) separate from the Review Shell
// (5173) and the FastAPI backend (8000), same as a real target app would.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    // The Review Shell iframes this app — some browsers block framing by
    // default via X-Frame-Options unless explicitly allowed; Vite's dev
    // server doesn't set that header, so no extra config is needed here for
    // same-origin-in-spirit local dev. A real deployment would need to
    // confirm its own framing policy allows the Review Shell's origin.
  },
});
