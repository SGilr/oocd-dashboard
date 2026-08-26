/**
 * Build time access to the derived tables.
 *
 * Everything is read from site/public/data, which scripts/stage-data.mjs fills
 * before the build. Nothing here runs in the browser and nothing fetches.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

const DATA_DIR = join(process.cwd(), "public", "data");

function load<T>(name: string): T {
  return JSON.parse(readFileSync(join(DATA_DIR, name), "utf8")) as T;
}

export type Basis = "closed" | "recorded";
export type FraudVariant = "all" | "ex_fraud";

/** The six out of court disposal types, in the order they are drawn. */
export const OOCD_TYPES = [8, 22, 3, 2, 6, 7] as const;
export type OocdType = (typeof OOCD_TYPES)[number];

export const OUTCOME_SHORT_LABELS: Record<number, string> = {
  0: "Not yet assigned an outcome",
  1: "Charge or summons",
  2: "Caution, youths",
  3: "Caution, adults",
  6: "Penalty notice for disorder",
  7: "Cannabis or khat warning",
  8: "Community resolution",
  22: "Outcome 22, diversionary activity",
};

export const BASIS_LABELS: Record<Basis, string> = {
  closed: "Outcomes for investigations closed in the quarter",
  recorded: "Outcomes for offences recorded in the quarter",
};

export const BASIS_SHORT: Record<Basis, string> = {
  closed: "Investigations closed",
  recorded: "Offences recorded",
};

export interface CountRow {
  force?: string;
  slug?: string;
  fy: string;
  q?: number;
  [column: string]: string | number | undefined;
}

interface Table<T> {
  meta: Record<string, unknown>;
  rows: T[];
}

export interface OffenceRow {
  force: string;
  slug: string;
  fy: string;
  offence_group: string;
  closed_oocd: number;
  closed_charge: number;
  recorded_oocd: number;
  recorded_charge: number;
}

export interface DenominatorRow {
  force: string;
  slug: string;
  fy: string;
  recorded_crime: number;
}

export interface BuildInfo {
  provenance: string;
  isFixture: boolean;
  dataRoot: string;
  manifestGeneratedAt: string | null;
  landingPage: string | null;
  attribution: string | null;
  builtAt: string;
  downloads: { name: string; bytes: number; sha256: string }[];
}

export const buildInfo = load<BuildInfo>("build-info.json");
export const manifest = load<Record<string, any>>("manifest.json");

export const forceYear = load<Table<CountRow>>("force_year.json");
export const forceQuarter = load<Table<CountRow>>("force_quarter.json");
export const nationalYear = load<Table<CountRow>>("national_year.json");
export const nationalQuarter = load<Table<CountRow>>("national_quarter.json");
export const forceOffenceYear = load<Table<OffenceRow>>("force_offence_year.json");
export const denominators = load<Table<DenominatorRow>>("denominators.json");
export const coverage = load<Record<string, any>>("coverage.json");

export const financialYears: string[] = (forceYear.meta.financial_years as string[]) ?? [];
export const latestYear: string = financialYears[financialYears.length - 1];
export const defaultBasis: Basis = ((forceYear.meta.default_basis as Basis) ?? "closed");

export const forces: { name: string; slug: string }[] = Array.from(
  new Map(forceYear.rows.map((row) => [row.slug as string, { name: row.force as string, slug: row.slug as string }])).values()
).sort((a, b) => a.name.localeCompare(b.name, "en-GB"));

/** Forces excluded from measures that normalise for force size. */
export const NO_DENOMINATOR_FORCES = new Set(["British Transport Police"]);

export function column(basis: Basis, variant: FraudVariant, name: string): string {
  return `${basis}_${variant}_${name}`;
}

export function value(row: CountRow, basis: Basis, variant: FraudVariant, name: string): number {
  return (row[column(basis, variant, name)] as number) ?? 0;
}

/** Sum the selected disposal types, so the disposal subset control works. */
export function oocdSum(
  row: CountRow,
  basis: Basis,
  variant: FraudVariant,
  types: readonly number[] = OOCD_TYPES
): number {
  let total = 0;
  for (const type of types) total += value(row, basis, variant, `t${type}`);
  return total;
}

export function quarterIndex(fy: string, q: number): number {
  return Number(fy.slice(0, 4)) * 4 + (q - 1);
}

/** A date used only to place a quarter on a time axis, at its mid point. */
export function quarterDate(fy: string, q: number): Date {
  const startYear = Number(fy.slice(0, 4));
  const month = 3 + (q - 1) * 3 + 1;
  return new Date(Date.UTC(startYear + (month > 11 ? 1 : 0), month % 12, 15));
}

export function recordedCrime(slug: string, fy: string): number | null {
  const row = denominators.rows.find((entry) => entry.slug === slug && entry.fy === fy);
  return row ? row.recorded_crime : null;
}
