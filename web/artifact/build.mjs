// Packages the verified dashboard into one self-contained HTML page (no server, no warehouse).
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { build } from "rolldown";

const here = path.dirname(new URL(import.meta.url).pathname);
const web = path.resolve(here, "..");
const out = process.argv[2] ?? path.join(here, "dist");
mkdirSync(out, { recursive: true });
const alias = { "@": path.join(web, "src") };

await build({ input: path.join(here, "dump.ts"), platform: "node", resolve: { alias },
  output: { file: path.join(out, "dump.mjs"), format: "esm" }, logLevel: "warn" });
const dataPath = path.join(out, "data.json");
execFileSync("node", [path.join(out, "dump.mjs"), dataPath], { cwd: web, stdio: "inherit" });

await build({ input: path.join(here, "entry.tsx"), platform: "browser", resolve: { alias },
  transform: { define: { "process.env.NODE_ENV": '"production"' } },
  output: { file: path.join(out, "app.js"), format: "iife", minify: true }, logLevel: "warn" });

const cssDir = path.join(web, ".next", "static", "chunks");
const cssFile = readdirSync(cssDir).find((f) => f.endsWith(".css"));
let css = readFileSync(path.join(cssDir, cssFile), "utf8").replace(/@font-face\{[^}]*\}/g, "");
const js = readFileSync(path.join(out, "app.js"), "utf8").replace(/<\/script/gi, "<\\/script");
const data = readFileSync(dataPath, "utf8").replace(/</g, "\\u003c");

const html = `<title>House of Minds</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link id="hom-fonts" rel="stylesheet" media="print" href="https://fonts.googleapis.com/css2?family=Geist:wght@300..700&family=Geist+Mono:wght@400;500&display=swap">
<style>
/* Single deliberate dark look (obsidian x champagne gold); colors are tokens in the app CSS. */
:root { --font-geist-sans: "Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-geist-mono: "Geist Mono", ui-monospace, Menlo, monospace; color-scheme: dark; }
:root[data-theme="light"] { --bg:#0b0b0d; --surface:#141418; --surface-2:#1b1b21; --line:#2a2a31; --text:#f3efe6;
  --muted:#a8a6a0; --gold:#d4b46a; --gold-soft:#d4b46a22; --pos:#4fb38a; --warn:#e0a843; --neg:#e06c62; --info:#7fa7d9; color-scheme: dark; }
html, body { background: #0b0b0d; }
header.sticky { top: env(safe-area-inset-top, 0px) !important; }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 40; background: #0b0b0d; }
#boot { padding: 48px 16px; color: #a8a6a0; font: 14px system-ui, sans-serif; }
${css}
</style>
<div id="root"><p id="boot">Loading House of Minds…</p></div>
<script type="application/json" id="hom-data">${data}</script>
<script>document.getElementById("hom-fonts").media = "all";</script>
<script>${js}</script>
`;
writeFileSync(path.join(out, "house-of-minds.html"), html);
console.log("wrote", path.join(out, "house-of-minds.html"), (html.length / 1e6).toFixed(2), "MB");
