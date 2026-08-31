# Content Provenance — Live Review extension (Phase 10)

Reviews a real, logged-in browser tab in-context — cookies, session, and
client-side routing all work because it's your own tab, not an anonymous
server-side fetch (that's Phase 8's `/api/v1/pages/render` instead). See
`ROADMAP.md`'s "Live-Session Bridge" section for the full design.

## Build

```bash
cd frontend
npm install
npm run build:extension
```

This builds `review-sdk/dist/{overlay,harvest}.js` first, then compiles the
extension's own scripts and assembles **both** loadable builds:

| Folder | Browser | Manifest difference |
|--------|---------|---------------------|
| `extension/dist/` | Chrome / Chromium / Edge | MV3 with `background.service_worker` |
| `extension/dist-firefox/` | Firefox | MV3 with a `background.scripts` event page + `browser_specific_settings.gecko.id` |

The extension's own code is identical for both — it uses the `chrome.*`
namespace, which Firefox also implements for MV3. Only the manifest differs
(`manifest.json` vs `manifest.firefox.json`).

## Load it

### Chrome / Chromium / Edge

1. Open `chrome://extensions`.
2. Enable **Developer mode** (top right).
3. **Load unpacked** → select `frontend/extension/dist/`.

### Firefox

1. Open `about:debugging#/runtime/this-firefox`.
2. **Load Temporary Add-on…** → select `frontend/extension/dist-firefox/manifest.json`.
3. It stays loaded until Firefox restarts (temporary add-ons aren't
   persisted). For a persistent install you'd need to package + sign it
   (`web-ext sign`, or upload to addons.mozilla.org) — out of scope for a
   dev tool.

## Use it

1. Run the backend (`uvicorn app.main:app --port 8001`) and the Review
   Shell (`npm run dev` in `frontend/`, port 5173).
2. Open the Review Shell's **Live (extension)** tab — it'll show "Waiting
   for the extension…" until a reviewed tab connects.
3. Navigate to the page you want to review in a normal tab, click the
   extension's toolbar icon, set source/target language, and click
   **Start reviewing this tab**.
4. Highlight boxes appear on the live page (no text is swapped — unlike
   Phase 8/9, this leaves the real page alone; see `harvest.ts`'s
   `rewrite()` docs for why). Click one to open the segment drawer back in
   the Review Shell's Live tab, exactly like the iframe-based modes.

The API base is hardcoded to `http://localhost:8001/api/v1`
(`harvest-content-script.ts`/`popup.ts`) — this whole extension is dev-only
for now, matching this project's other dev-focused defaults (e.g.
`ReviewPage.tsx`'s `DEFAULT_TARGET_BASE`).

## Rebuilding after a change

Re-run `npm run build:extension`, then reload the extension:

- **Chrome**: click the refresh icon on the extension's card in
  `chrome://extensions`.
- **Firefox**: click **Reload** next to the add-on in
  `about:debugging#/runtime/this-firefox`.

Neither browser hot-reloads an unpacked / temporary extension.

## Troubleshooting ("Waiting for the extension…" never turns to Connected)

The `tu:ready` message has to travel: reviewed tab → background → Review
Shell tab. Check each hop:

1. **Reviewed tab's own console** (F12 on that page) — look for
   `[review-extension] harvested N element(s)` then `harvest matching
   failed`. A failed `fetch` to `http://localhost:8001` is the usual
   culprit; the manifest's `host_permissions: ["http://localhost:8001/*"]`
   is what makes that fetch bypass the page's CSP/CORS. Firefox may ask you
   to grant that host permission the first time — accept it (`about:addons`
   → the add-on → Permissions).
2. **Background script console** — `about:debugging#/runtime/this-firefox`
   (or `chrome://extensions`) → the add-on's **Inspect** button. You should
   see `Review Shell registered on tab …` and `now reviewing tab …`.
3. **Review Shell must be on `localhost:5173` or `localhost:8001`** — the
   `bridge-content-script` only auto-injects on those origins (manifest
   `content_scripts.matches`). A different port = no bridge = never
   connects.
4. The backend must be reachable at `http://localhost:8001` (the API base
   is hard-coded — see `harvest-content-script.ts` / `popup.ts`).
