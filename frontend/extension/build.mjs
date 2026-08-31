// build.mjs — assembles the loadable extension into extension/dist/ (Chrome
// / Chromium, Manifest V3 service worker) AND extension/dist-firefox/
// (Firefox, MV3 with a background.scripts event page + a gecko add-on id).
// Run via `npm run build:extension` (frontend/package.json), which builds
// review-sdk first (npm run build:sdk) so overlay.js/harvest.js exist to
// copy in. chrome.scripting.executeScript's `files` paths are relative to
// the extension's own root, so those compiled bundles have to physically
// live inside each dist tree — they can't be referenced from
// frontend/review-sdk/dist/ directly.
//
// The two builds share every compiled .js and popup.html; they differ ONLY
// by manifest (manifest.json vs manifest.firefox.json). The extension's own
// scripts use the `chrome.*` namespace, which Firefox also provides for MV3
// — nothing browser-specific in the code itself.
import { execSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, "..");
const chromeDir = join(__dirname, "dist");
const firefoxDir = join(__dirname, "dist-firefox");
const sdkDist = join(frontendRoot, "review-sdk", "dist");

for (const file of ["overlay.js", "harvest.js"]) {
  if (!existsSync(join(sdkDist, file))) {
    console.error(`${join(sdkDist, file)} not found — run \`npm run build:sdk\` first.`);
    process.exit(1);
  }
}

rmSync(chromeDir, { recursive: true, force: true });
rmSync(firefoxDir, { recursive: true, force: true });

// tsc emits the extension's own scripts straight into extension/dist/
// (tsconfig.json's outDir) — the Chrome build's directory. The Firefox
// build copies the same .js out of it below.
mkdirSync(join(chromeDir, "review-sdk"), { recursive: true });
execSync("npx tsc -p extension/tsconfig.json", { cwd: frontendRoot, stdio: "inherit" });

// Assets common to both builds: the review-sdk bundles and the popup page.
function copyShared(targetDir) {
  mkdirSync(join(targetDir, "review-sdk"), { recursive: true });
  cpSync(join(sdkDist, "overlay.js"), join(targetDir, "review-sdk", "overlay.js"));
  cpSync(join(sdkDist, "harvest.js"), join(targetDir, "review-sdk", "harvest.js"));
  cpSync(join(__dirname, "popup.html"), join(targetDir, "popup.html"));
}

// ── Chrome / Chromium ──────────────────────────────────────────────────
copyShared(chromeDir);
cpSync(join(__dirname, "manifest.json"), join(chromeDir, "manifest.json"));

// ── Firefox ───────────────────────────────────────────────────────────
mkdirSync(firefoxDir, { recursive: true });
for (const entry of readdirSync(chromeDir, { withFileTypes: true })) {
  if (entry.isFile() && entry.name.endsWith(".js")) {
    cpSync(join(chromeDir, entry.name), join(firefoxDir, entry.name));
  }
}
copyShared(firefoxDir);
cpSync(join(__dirname, "manifest.firefox.json"), join(firefoxDir, "manifest.json"));

console.log("\nChrome/Chromium  -> frontend/extension/dist/");
console.log("  chrome://extensions -> Developer mode -> Load unpacked -> that folder");
console.log("Firefox          -> frontend/extension/dist-firefox/");
console.log("  about:debugging#/runtime/this-firefox -> Load Temporary Add-on -> that folder's manifest.json");
