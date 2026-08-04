// build.mjs — assembles the loadable extension into extension/dist/.
// Run via `npm run build:extension` (frontend/package.json), which builds
// review-sdk first (npm run build:sdk) so overlay.js/harvest.js exist to
// copy in. chrome.scripting.executeScript's `files` paths are relative to
// the extension's own root, so those compiled bundles have to physically
// live inside this directory tree — they can't be referenced from
// frontend/review-sdk/dist/ directly.
import { execSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, "..");
const distDir = join(__dirname, "dist");
const sdkDist = join(frontendRoot, "review-sdk", "dist");

for (const file of ["overlay.js", "harvest.js"]) {
  if (!existsSync(join(sdkDist, file))) {
    console.error(`${join(sdkDist, file)} not found — run \`npm run build:sdk\` first.`);
    process.exit(1);
  }
}

rmSync(distDir, { recursive: true, force: true });
mkdirSync(join(distDir, "review-sdk"), { recursive: true });

execSync("npx tsc -p extension/tsconfig.json", { cwd: frontendRoot, stdio: "inherit" });

cpSync(join(sdkDist, "overlay.js"), join(distDir, "review-sdk", "overlay.js"));
cpSync(join(sdkDist, "harvest.js"), join(distDir, "review-sdk", "harvest.js"));
cpSync(join(__dirname, "manifest.json"), join(distDir, "manifest.json"));
cpSync(join(__dirname, "popup.html"), join(distDir, "popup.html"));

console.log("\nExtension built to frontend/extension/dist/");
console.log("Load it via chrome://extensions -> Developer mode -> Load unpacked -> select that folder.");
