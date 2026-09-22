#!/usr/bin/env node
/**
 * Contrast and separation for the six resolution series.
 *
 * The bands on the mix charts, and the lines drawn from the same tokens, are
 * graphical objects a reader has to perceive to read the chart, so WCAG 1.4.11
 * asks for 3:1 against the surface they sit on. That surface is --surface-1,
 * which is what .figure__plot sets.
 *
 * Three of them did not clear it. In the light theme the amber was 2.17:1, the
 * pink 2.69:1 and the green 2.82:1. Nothing caught that, because axe does not
 * measure the contrast of an SVG stroke or fill, and the palette check that
 * already existed covers the capacity page only.
 *
 * The fix darkened those three by scaling their linear RGB, which preserves
 * hue and saturation exactly and changes only luminance, so the series kept
 * their identity.
 *
 * On the two thresholds:
 *
 *   contrast    3:1, and it is not negotiable. It is the accessibility floor.
 *
 *   separation  5, not the 8 the capacity page sets for itself. That is a
 *               deliberate difference. On /capacity colour is the only channel
 *               carrying the measured against modelled distinction, so it has
 *               to do all the work. Here every band also carries a texture, a
 *               legend entry and a row in the table beside the chart. The dark
 *               palette has sat at 5.2 since it was written, so 8 was never
 *               this palette's working standard; 5 holds the line where it
 *               actually is and still catches two series collapsing together.
 *
 * Colour vision deficiency is simulated by Vienot, Brettel and Mollon 1999.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "..", "src", "styles", "global.css"), "utf8");
const palette = readFileSync(join(here, "..", "src", "lib", "palette.ts"), "utf8");

const MEDIA = "@media (prefers-color-scheme: dark)";
const THEME = ':root[data-theme="dark"]';
const END = "*,\n*::before";

function token(name, from, to) {
  const start = css.indexOf(from);
  const end = to ? css.indexOf(to, start) : css.length;
  const match = css.slice(start, end).match(new RegExp(`--${name}\\s*:\\s*([^;]+);`));
  if (!match) throw new Error(`--${name} is not defined in the ${from} scope`);
  return match[1].trim();
}

// The six series plus the charge comparator, which is drawn from the same
// family and sits on the same surface.
const MARKS = ["series-8", "series-22", "series-3", "series-2", "series-6", "series-7", "series-1"];
const SCOPES = { light: [":root {", MEDIA], dark: [THEME, END] };
const VISION = ["normal", "protanopia", "deuteranopia"];
const CONTRAST_TARGET = 3;
const SEPARATION_TARGET = 5;

const rgb = (hex) => {
  const value = hex.replace("#", "");
  const full = value.length === 3 ? value.split("").map((c) => c + c).join("") : value;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255);
};
const linear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const gamma = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.max(c, 0) ** (1 / 2.4) - 0.055);

function luminance(hex) {
  const [r, g, b] = rgb(hex).map(linear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
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
  protanopia: [[0, 2.02344, -2.52581], [0, 1, 0], [0, 0, 1]],
  deuteranopia: [[1, 0, 0], [0.494207, 0, 1.24827], [0, 0, 1]],
};
const apply = (m, v) => m.map((row) => row.reduce((sum, k, i) => sum + k * v[i], 0));

function simulate(hex, kind) {
  if (kind === "normal") return hex;
  const out = apply(LMS_TO_RGB, apply(COLLAPSE[kind], apply(RGB_TO_LMS, rgb(hex).map(linear))));
  return (
    "#" +
    out
      .map((c) => Math.round(Math.min(1, Math.max(0, gamma(c))) * 255))
      .map((c) => c.toString(16).padStart(2, "0"))
      .join("")
  );
}

const problems = [];
let worstSeparation = Infinity;
let worstWhere = "";

for (const [theme, [from, to]] of Object.entries(SCOPES)) {
  const surface = token("surface-1", from, to);
  const colours = Object.fromEntries(MARKS.map((name) => [name, token(name, from, to)]));

  for (const mark of MARKS) {
    const ratio = contrast(colours[mark], surface);
    if (ratio < CONTRAST_TARGET) {
      problems.push(
        `${theme}: --${mark} is ${ratio.toFixed(2)}:1 against --surface-1, below ${CONTRAST_TARGET}:1`
      );
    }
  }

  for (let i = 0; i < MARKS.length; i += 1) {
    for (let j = i + 1; j < MARKS.length; j += 1) {
      for (const vision of VISION) {
        const distance = deltaE(simulate(colours[MARKS[i]], vision), simulate(colours[MARKS[j]], vision));
        if (distance < worstSeparation) {
          worstSeparation = distance;
          worstWhere = `${theme}, ${vision}, --${MARKS[i]} and --${MARKS[j]}`;
        }
        if (distance < SEPARATION_TARGET) {
          problems.push(
            `${theme}, ${vision}: --${MARKS[i]} and --${MARKS[j]} are Delta E ` +
              `${distance.toFixed(1)} apart, below ${SEPARATION_TARGET}`
          );
        }
      }
    }
  }
}

// The same hex values live in global.css and in palette.ts, and the charts
// read whichever the mark happens to use. If those two drift apart, a band and
// its own legend swatch stop being the same colour, and nothing else notices.
for (const [theme, [from, to]] of Object.entries(SCOPES)) {
  for (const mark of MARKS) {
    const type = mark.replace("series-", "");
    const block = palette.match(new RegExp(`type:\\s*${type},[^}]*}`, "s"));
    if (!block) continue;
    const declared = block[0].match(new RegExp(`${theme}:\\s*"([^"]+)"`));
    if (!declared) continue;
    const inCss = token(mark, from, to).toLowerCase();
    if (declared[1].toLowerCase() !== inCss) {
      problems.push(
        `${theme}: --${mark} is ${inCss} in global.css but ${declared[1]} in palette.ts`
      );
    }
  }
}

if (problems.length) {
  console.error("The resolution series palette does not clear its targets:\n");
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}

console.log(
  `Series palette clears its targets: every mark at or above ${CONTRAST_TARGET}:1 on ` +
    `--surface-1 in both themes, worst all-pairs separation Delta E ` +
    `${worstSeparation.toFixed(1)} (${worstWhere}) against a floor of ${SEPARATION_TARGET}, ` +
    `and global.css agrees with palette.ts.`
);
