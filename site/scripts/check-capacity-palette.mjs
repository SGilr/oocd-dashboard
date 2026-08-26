#!/usr/bin/env node
/**
 * Colour separation and contrast for the marks on /capacity.
 *
 * The capacity page carries three route colours in its demand cascade and one
 * modelled colour in its calculator, and the whole argument of the page rests
 * on a reader telling the modelled figures from the measured ones. If two of
 * those marks collapse together for a reader with anomalous colour vision, the
 * epistemic distinction the page is built on stops existing for them.
 *
 * The kit that specified this page carried a validated palette and the
 * instruction to re-validate if any hue changed. One did: the prosecution
 * route moved off the kit's #2a78d6, because that value is the community
 * resolution series on the other four pages of this site and one hue cannot
 * mean diversion there and prosecution here. This script is the re-validation.
 *
 * Two checks, both against the target the kit set:
 *
 *   separation  every pair of marks at least Delta E 8 (CIE76) as seen by
 *               normal trichromats, by protanopes and by deuteranopes
 *   contrast    every mark at least 3:1 against the surface it sits on,
 *               which is WCAG 1.4.11 for a non-text graphical object
 *
 * Colour vision deficiency is simulated by the Vienot, Brettel and Mollon
 * 1999 method, the standard linear LMS projection for dichromats.
 *
 * Colour is never the only channel on this page: every bar carries a text
 * label with its own percentage and every modelled figure carries a badge.
 * This check is the floor, not the whole accessibility argument.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "src", "styles", "global.css"),
  "utf8"
);

/** Read a token's value out of one of the three theme scopes. */
function token(name, scopeStart, scopeEnd) {
  const start = css.indexOf(scopeStart);
  const end = scopeEnd ? css.indexOf(scopeEnd, start) : css.length;
  const match = css.slice(start, end).match(new RegExp(`--${name}\\s*:\\s*([^;]+);`));
  if (!match) throw new Error(`--${name} is not defined in the ${scopeStart} scope`);
  return match[1].trim();
}

const MEDIA = "@media (prefers-color-scheme: dark)";
const THEME = ':root[data-theme="dark"]';
const END = "*,\n*::before";

const MARKS = ["route-oocd", "route-court", "ink-2", "modelled"];
const SURFACES = { light: "surface-2", dark: "surface-2" };

const themes = {
  light: Object.fromEntries(
    [...MARKS, SURFACES.light].map((name) => [name, token(name, ":root {", MEDIA)])
  ),
  dark: Object.fromEntries(
    [...MARKS, SURFACES.dark].map((name) => [name, token(name, THEME, END)])
  ),
};

function rgb(hex) {
  const value = hex.replace("#", "");
  const full =
    value.length === 3
      ? value
          .split("")
          .map((c) => c + c)
          .join("")
      : value;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255);
}

const linear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const gamma = (c) =>
  c <= 0.0031308 ? 12.92 * c : 1.055 * Math.max(c, 0) ** (1 / 2.4) - 0.055;

function relativeLuminance(hex) {
  const [r, g, b] = rgb(hex).map(linear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [x, y] = [relativeLuminance(a), relativeLuminance(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}

function lab(hex) {
  const [r, g, b] = rgb(hex).map(linear);
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29);
  const [fx, fy, fz] = [f(x), f(y), f(z)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function deltaE(a, b) {
  const [l1, a1, b1] = lab(a);
  const [l2, a2, b2] = lab(b);
  return Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}

// Vienot, Brettel and Mollon 1999. Linear RGB to LMS, collapse the missing
// cone onto the plane the dichromat can see, and come back.
const RGB_TO_LMS = [
  [17.8824, 43.5161, 4.11935],
  [3.45565, 27.1554, 3.86714],
  [0.0299566, 0.184309, 1.46709],
];
const LMS_TO_RGB = [
  [0.080944, -0.130504, 0.116721],
  [-0.0102485, 0.0540194, -0.113615],
  [-0.000365294, -0.00412163, 0.693513],
];
const COLLAPSE = {
  protanopia: [
    [0, 2.02344, -2.52581],
    [0, 1, 0],
    [0, 0, 1],
  ],
  deuteranopia: [
    [1, 0, 0],
    [0.494207, 0, 1.24827],
    [0, 0, 1],
  ],
};

const apply = (m, v) => m.map((row) => row.reduce((sum, k, i) => sum + k * v[i], 0));

function simulate(hex, kind) {
  if (kind === "normal") return hex;
  const linearRgb = rgb(hex).map(linear);
  const out = apply(LMS_TO_RGB, apply(COLLAPSE[kind], apply(RGB_TO_LMS, linearRgb)));
  return (
    "#" +
    out
      .map((c) => Math.round(Math.min(1, Math.max(0, gamma(c))) * 255))
      .map((c) => c.toString(16).padStart(2, "0"))
      .join("")
  );
}

const SEPARATION_TARGET = 8;
const CONTRAST_TARGET = 3;
const VISION = ["normal", "protanopia", "deuteranopia"];

const problems = [];
let worstSeparation = Infinity;

for (const [themeName, colours] of Object.entries(themes)) {
  const surface = colours[SURFACES[themeName]];

  for (const mark of MARKS) {
    const ratio = contrast(colours[mark], surface);
    if (ratio < CONTRAST_TARGET) {
      problems.push(
        `${themeName}: --${mark} is ${ratio.toFixed(2)}:1 against the surface, ` +
          `below ${CONTRAST_TARGET}:1`
      );
    }
  }

  for (let i = 0; i < MARKS.length; i += 1) {
    for (let j = i + 1; j < MARKS.length; j += 1) {
      for (const vision of VISION) {
        const distance = deltaE(
          simulate(colours[MARKS[i]], vision),
          simulate(colours[MARKS[j]], vision)
        );
        worstSeparation = Math.min(worstSeparation, distance);
        if (distance < SEPARATION_TARGET) {
          problems.push(
            `${themeName}, ${vision}: --${MARKS[i]} and --${MARKS[j]} are ` +
              `Delta E ${distance.toFixed(1)} apart, below ${SEPARATION_TARGET}`
          );
        }
      }
    }
  }
}

if (problems.length) {
  console.error("The capacity page palette does not clear its targets:\n");
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}

console.log(
  `Capacity palette clears its targets: worst all-pairs separation ` +
    `Delta E ${worstSeparation.toFixed(1)} across normal, protanopic and ` +
    `deuteranopic vision in both themes, against a target of ${SEPARATION_TARGET}, ` +
    `and every mark at or above ${CONTRAST_TARGET}:1 on its surface.`
);
