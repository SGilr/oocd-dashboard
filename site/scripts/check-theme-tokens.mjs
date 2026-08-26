#!/usr/bin/env node
/**
 * Every colour token must be defined in all three theme scopes.
 *
 * The stylesheet defines the light palette on `:root`, then redefines the dark
 * values twice: once under `prefers-color-scheme: dark` for the viewer's system
 * setting, and once under `:root[data-theme="dark"]` for an explicit choice.
 * A token defined in one dark scope and not the other looks correct in whichever
 * the author happened to test, and wrong in the other.
 *
 * That is not hypothetical. `--band-fill`, the interquartile band on the force
 * pages, was defined for system dark and not for an explicit dark choice, so
 * anyone who chose dark deliberately saw a light band on a dark chart. Nothing
 * caught it, because both scopes were individually valid CSS.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "src", "styles", "global.css"),
  "utf8"
);

function scope(from, to) {
  const start = css.indexOf(from);
  const end = to ? css.indexOf(to) : css.length;
  if (start < 0 || end < 0) {
    throw new Error(`Could not find the ${from} block in global.css`);
  }
  return new Set([...css.slice(start, end).matchAll(/--([a-z0-9-]+)\s*:/g)].map((m) => m[1]));
}

const MEDIA = "@media (prefers-color-scheme: dark)";
const THEME = ':root[data-theme="dark"]';
const END = "*,\n*::before";

const root = scope(":root {", MEDIA);
const systemDark = scope(MEDIA, THEME);
const chosenDark = scope(THEME, END);

const problems = [];
for (const token of systemDark) {
  if (!chosenDark.has(token)) {
    problems.push(`--${token} is redefined for system dark but not for a chosen dark theme`);
  }
}
for (const token of chosenDark) {
  if (!systemDark.has(token)) {
    problems.push(`--${token} is redefined for a chosen dark theme but not for system dark`);
  }
}
for (const token of systemDark) {
  if (!root.has(token)) {
    problems.push(`--${token} has a dark value but no light value on :root`);
  }
}

if (problems.length) {
  console.error("Theme tokens do not agree across scopes:\n");
  for (const problem of problems) console.error(`  ${problem}`);
  console.error(`\n${problems.length} problem(s). The dark theme will be wrong for some viewers.`);
  process.exit(1);
}

console.log(
  `Theme tokens agree: ${root.size} on :root, ${systemDark.size} redefined in both dark scopes.`
);
