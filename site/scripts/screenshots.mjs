#!/usr/bin/env node
/**
 * Regenerate docs/screenshots/ from the current build.
 *
 * Run after `npm run build`. The screenshots show the layout, the palette, the
 * textures and both themes. If the build was made from fixtures, every page
 * carries the banner saying the figures are invented, and the screenshots show
 * it, which is the intended behaviour rather than a defect in them.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { serveDist } from "./serve-dist.mjs";

const OUT = "../docs/screenshots";
const SHOTS = [
  ["/", "overview", "light", 1280, 1500],
  ["/", "overview-dark", "dark", 1280, 1500],
  ["/", "overview-mobile", "light", 390, 1400],
  ["/compare", "compare", "light", 1440, 1400],
  ["/force/west-yorkshire", "force-west-yorkshire", "light", 1280, 1600],
  ["/force/west-yorkshire", "force-west-yorkshire-dark", "dark", 1280, 1600],
  ["/methodology", "methodology", "light", 1100, 1400],
  ["/data", "data", "light", 1280, 1200],
];

mkdirSync(OUT, { recursive: true });
const server = await serveDist(4321);
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});

let failures = 0;
for (const [path, name, colorScheme, width, height] of SHOTS) {
  const context = await browser.newContext({ colorScheme, viewport: { width, height } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto(`${server.url}${path}`, { waitUntil: "networkidle" });
  await page.screenshot({ path: `${OUT}/${name}.png` });
  if (errors.length) {
    failures += 1;
    console.error(`${name}: ${errors.length} page error(s)`, errors.slice(0, 3));
  } else {
    console.log(`${name}: ok`);
  }
  await context.close();
}

await browser.close();
server.close();
process.exit(failures ? 1 : 0);
