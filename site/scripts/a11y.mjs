#!/usr/bin/env node
/**
 * Run axe against every page type, in both themes, and fail on any violation.
 *
 * WCAG 2.1 AA is a requirement of this dashboard, not an aspiration, so this
 * runs against the built site rather than against a development server, and it
 * exits non zero so it can gate a build.
 *
 * Run after `npm run build`.
 */
import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import { serveDist } from "./serve-dist.mjs";

const PAGES = ["/", "/compare", "/force/west-yorkshire", "/methodology", "/data"];
const THEMES = ["light", "dark"];
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

const axe = readFileSync("node_modules/axe-core/axe.min.js", "utf8");
const server = await serveDist(4322);
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});

let total = 0;
for (const colorScheme of THEMES) {
  for (const path of PAGES) {
    const context = await browser.newContext({ colorScheme, viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${server.url}${path}`, { waitUntil: "networkidle" });
    await page.addScriptTag({ content: axe });
    const result = await page.evaluate(
      async (tags) => await window.axe.run(document, { runOnly: { type: "tag", values: tags } }),
      TAGS
    );
    total += result.violations.length;
    console.log(`${colorScheme.padEnd(5)} ${path.padEnd(28)} ${result.violations.length} violations`);
    for (const violation of result.violations) {
      console.log(`      [${violation.impact}] ${violation.id}: ${violation.help}`);
      for (const node of violation.nodes.slice(0, 3)) console.log(`         ${node.target}`);
    }
    await context.close();
  }
}

await browser.close();
server.close();

if (total) {
  console.error(`\n${total} accessibility violations. The build should not ship.`);
  process.exit(1);
}
console.log("\nNo accessibility violations.");
