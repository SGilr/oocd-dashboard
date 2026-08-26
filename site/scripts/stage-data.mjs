#!/usr/bin/env node
/**
 * Copy the derived tables into the site's public directory before the build.
 *
 * The site reads its figures from site/public/data, so the pages and the
 * download links on /data are served from one set of files. Nothing is
 * transformed here, the files are copied byte for byte, and the checksums on
 * the data page are computed from the copies.
 *
 * The data root is data/ by default. When that has not been built, the
 * synthetic fixture tree is used instead and build-info.json records
 * provenance "fixture", which puts a banner on every page.
 */
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(siteRoot, "..");

const explicit = process.env.OOCD_DATA_ROOT ? resolve(process.env.OOCD_DATA_ROOT) : null;
const live = join(repoRoot, "data");
const fixture = join(repoRoot, "data", "fixture");

function usable(root) {
  return existsSync(join(root, "processed", "force_year.json"));
}

let dataRoot = explicit ?? (usable(live) ? live : fixture);
if (!usable(dataRoot)) {
  console.error(
    `\nNo derived tables found under ${dataRoot}.\n` +
      `Run the extract first:\n` +
      `  python etl/fetch.py && python etl/transform.py && python etl/validate.py\n` +
      `or build against fixtures:\n` +
      `  python etl/make_fixtures.py && python etl/transform.py --data-root fixture\n`
  );
  process.exit(1);
}

const target = join(siteRoot, "public", "data");
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(join(dataRoot, "processed"), target, { recursive: true });

for (const name of ["manifest.json", "validation-report.json"]) {
  const source = join(dataRoot, name);
  if (existsSync(source)) cpSync(source, join(target, name));
}

const manifest = JSON.parse(readFileSync(join(target, "manifest.json"), "utf8"));

const downloads = readdirSync(target)
  .filter((name) => /\.(csv|json)$/.test(name) && name !== "build-info.json")
  .sort()
  .map((name) => {
    const path = join(target, name);
    return {
      name,
      bytes: statSync(path).size,
      sha256: createHash("sha256").update(readFileSync(path)).digest("hex"),
    };
  });

const buildInfo = {
  provenance: manifest.provenance ?? "unknown",
  isFixture: manifest.provenance === "fixture",
  dataRoot: dataRoot.replace(repoRoot, "").replace(/^\//, "") || "data",
  manifestGeneratedAt: manifest.generated_at ?? null,
  landingPage: manifest.landing_page ?? null,
  attribution: manifest.attribution ?? null,
  builtAt: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  downloads,
};
writeFileSync(join(target, "build-info.json"), JSON.stringify(buildInfo, null, 1) + "\n");

console.log(`Staged ${downloads.length} data files from ${dataRoot}`);
console.log(`Provenance: ${buildInfo.provenance}`);
if (buildInfo.isFixture) {
  console.log("The build carries synthetic fixture data and must not be published.");
}
